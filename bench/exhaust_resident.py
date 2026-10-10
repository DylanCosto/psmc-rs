"""Isolated resident-message go/no-go probe, exact binary64 oracle comparison."""
import ctypes as C,json,os,struct,subprocess,time
from pathlib import Path
from common import ROOT,save,sha256
P=C.c_void_p; I=C.c_int; U=C.c_uint; Z=C.c_size_t; D=C.c_uint64

def bind(lib,name,args):
    f=getattr(lib,name);f.argtypes=args;f.restype=I
    def call(*a):
        code=f(*a)
        if code:raise RuntimeError(f'{name}: {code}')
    return call

def main():
    os.chdir(ROOT);raw=Path('work/exhaust/resident');raw.mkdir(parents=True)
    lib=json.loads(Path('bench/cuda-environment.json').read_text())['nvrtc_path'];nv=C.CDLL(lib);cu=C.CDLL('libcuda.so.1')
    program=P();source=Path('bench/cuda_resident.cu').read_text()
    source=source.replace('int n,int start,int end) {','int n,int start,int end,int length) {\n initial += (long long)blockIdx.x*n; a += (long long)blockIdx.x*n*n; e += (long long)blockIdx.x*3*n; obs += (long long)blockIdx.x*length; f += (long long)blockIdx.x*(length+1)*n; scales += (long long)blockIdx.x*(length+1);')
    source=source.replace('int n,int length,int start,int end) {','int n,int length,int start,int end) {\n ae += (long long)blockIdx.x*3*n*n; obs += (long long)blockIdx.x*length; scales += (long long)blockIdx.x*(length+1); b += (long long)blockIdx.x*(length+1)*n;')
    (raw/'batched.cu').write_text(source); source=source.encode()
    bind(nv,'nvrtcCreateProgram',[C.POINTER(P),C.c_char_p,C.c_char_p,I,P,P])(C.byref(program),source,b'probe.cu',0,None,None)
    opts=[b'--gpu-architecture=compute_75',b'--fmad=false',b'--ftz=false',b'--prec-div=true'];options=(C.c_char_p*len(opts))(*opts)
    bind(nv,'nvrtcCompileProgram',[P,I,C.POINTER(C.c_char_p)])(program,len(opts),options)
    size=Z();bind(nv,'nvrtcGetPTXSize',[P,C.POINTER(Z)])(program,C.byref(size));ptx=C.create_string_buffer(size.value)
    bind(nv,'nvrtcGetPTX',[P,P])(program,ptx);(raw/'kernel.ptx').write_bytes(ptx.raw)
    assert b'fma.rn.f64' not in ptx.raw
    bind(nv,'nvrtcDestroyProgram',[C.POINTER(P)])(C.byref(program))
    bind(cu,'cuInit',[U])(0);dev=I();bind(cu,'cuDeviceGet',[C.POINTER(I),I])(C.byref(dev),0)
    ctx=P();bind(cu,'cuDevicePrimaryCtxRetain',[C.POINTER(P),I])(C.byref(ctx),dev);bind(cu,'cuCtxSetCurrent',[P])(ctx)
    module=P();bind(cu,'cuModuleLoadData',[C.POINTER(P),P])(C.byref(module),ptx)
    functions=[]
    for name in [b'forward',b'backward']:
        f=P();bind(cu,'cuModuleGetFunction',[C.POINTER(P),P,C.c_char_p])(C.byref(f),module,name);functions.append(f)
    alloc=bind(cu,'cuMemAlloc_v2',[C.POINTER(D),Z]);free=bind(cu,'cuMemFree_v2',[D]);upload=bind(cu,'cuMemcpyHtoD_v2',[D,P,Z]);download=bind(cu,'cuMemcpyDtoH_v2',[P,D,Z]);sync=bind(cu,'cuCtxSynchronize',[])
    launch=bind(cu,'cuLaunchKernel',[P,U,U,U,U,U,U,U,P,C.POINTER(P),P])
    report={'status':'running','kernel_sha256':sha256(raw/'batched.cu'),'ptx_sha256':sha256(raw/'kernel.ptx'),'options':[v.decode() for v in opts],'cases':[]}
    for batch in [1,8,16,32]:
        length=50001
        fixture=raw/f'{length}.bin';cmd=['work/exhaust/cpu/baseline/target/release/examples/cuda_fixture',str(length),str(fixture)]
        measured=json.loads(subprocess.check_output(cmd));data=fixture.read_bytes();n,L=struct.unpack_from('<QQ',data);pos=16;arrays=[]
        for count in [n,n*n,3*n,3*n*n,(L+1)*n,(L+1)*n,L+1]:
            arrays.append(data[pos:pos+count*8]);pos+=count*8
        arrays.append(data[pos:]);device=[]
        start=time.perf_counter()
        for a in arrays:
            p=D();alloc(C.byref(p),len(a)*batch);device.append(p)
        # Zero outputs except scale[0]=1, retain the CPU results for comparison.
        initial=list(arrays);initial[4]=bytes(len(arrays[4]));initial[5]=bytes(len(arrays[5]));initial[6]=struct.pack('<d',1.0)+bytes(len(arrays[6])-8)
        for p,a in zip(device,initial):upload(p,C.c_char_p(a*batch),len(a)*batch)
        sync();compute=time.perf_counter()
        for s in range(1,L+1,2048):
            args=[device[0],device[1],device[2],device[7],device[4],device[6],I(n),I(s),I(min(s+2048,L+1)),I(L)]
            pointers=(P*len(args))(*(C.cast(C.byref(v),P) for v in args));launch(functions[0],batch,1,1,64,1,1,0,None,pointers,None)
        for s in range(L,0,-2048):
            args=[device[3],device[7],device[6],device[5],I(n),I(L),I(s),I(max(s-2047,1))]
            pointers=(P*len(args))(*(C.cast(C.byref(v),P) for v in args));launch(functions[1],batch,1,1,64,1,1,0,None,pointers,None)
        sync();compute=time.perf_counter()-compute
        mismatch=[]
        for i in [4,5,6]:
            got=C.create_string_buffer(len(arrays[i])*batch);download(got,device[i],len(arrays[i])*batch)
            if got.raw!=arrays[i]*batch:mismatch.append(i)
        elapsed=time.perf_counter()-start
        for p in device:free(p)
        case=dict(batch=batch,**measured,command=cmd,fixture_sha256=sha256(fixture),gpu_kernel_seconds=compute,gpu_alloc_transfer_compute_seconds=elapsed,mismatched_arrays=mismatch)
        report['cases'].append(case);save('bench/exhaust-resident.json',report);print(case,flush=True)
        assert not mismatch
    bind(cu,'cuModuleUnload',[P])(module);bind(cu,'cuDevicePrimaryCtxRelease_v2',[I])(dev)
    report['status']='passed_exactness';report['decision']='Compare batched kernels to measured independent CPU messages; synthetic repeated fixture is an occupancy probe, not an inference speed claim.';save('bench/exhaust-resident.json',report)
if __name__=='__main__':main()
