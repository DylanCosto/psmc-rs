"""Independent high-precision transcription of pinned core.c model equations.
Diagnostic only. Probabilities are finally rounded to f64 for the dense HMM.
"""
from decimal import Decimal as D, localcontext
import math

def model(params, groups, precision=50):
    with localcontext() as ctx:
        ctx.prec=precision
        p=[D.from_float(float(x)) for x in params]
        n=len(groups); theta,rho,mt=p[:3]; lam=[p[3+g] for g in groups]
        beta=(1+mt/D('0.1')).ln()/(n-1)
        t=[D('0.1')*((beta*k).exp()-1) for k in range(n-1)]+[mt,D(1000)]
        tau=[t[k+1]-t[k] for k in range(n)]
        alpha=[D(1)]
        for k in range(1,n): alpha.append(alpha[-1]*(-tau[k-1]/lam[k-1]).exp())
        alpha.append(D(0)); b=[D(0)]
        for k in range(1,n): b.append(b[-1]+lam[k-1]*(1/alpha[k]-1/alpha[k-1]))
        qa=[(alpha[k]-alpha[k+1])*(b[k]-lam[k]/alpha[k])+tau[k] for k in range(n-1)]
        cpi=sum(lam[k]*(alpha[k]-alpha[k+1]) for k in range(n)); cs=1/(cpi*rho)+D('0.5')
        initial=[]; trans=[]; homo=[]; hetero=[]; elapsed=D(0)
        for k in range(n):
            ak=alpha[k]-alpha[k+1]; lk=lam[k]
            cp=ak*(elapsed+lk)-alpha[k+1]*tau[k]; pi=cp/cpi
            sig=(ak/(cpi*rho)+pi/2)/cs
            remainder=1-pi/(cs*sig)
            # C log returns NaN/-Inf here and takes the existing interval fallback.
            # Decimal raises instead, so express that same branch explicitly.
            avg=-remainder.ln()/rho if remainder>0 else D('NaN')
            if avg.is_nan() or avg<elapsed or avg>elapsed+tau[k]: avg=elapsed+lk-tau[k]*alpha[k+1]/ak
            q=[]
            for j in range(n):
                if j<k: v=ak/cp*qa[j]
                elif j>k: v=(alpha[j]-alpha[j+1])*qa[k]/cp
                else: v=(ak*ak*(b[k]-lk/alpha[k])+2*lk*ak-2*alpha[k+1]*tau[k])/cp
                q.append(v)
            tmp=pi/(cs*sig)
            row=[tmp*v+(1-tmp if j==k else 0) for j,v in enumerate(q)]
            initial.append(sig);trans.extend(row)
            emission=(-theta*avg).exp();homo.append(emission);hetero.append(1-emission)
            elapsed+=tau[k]
        values=[float(x) for x in initial+trans+homo+hetero+[D(1)]*n]
        assert all(math.isfinite(x) and 0<=x<=1 for x in values)
        assert abs(sum(values[:n])-1)<1e-12
        for k in range(n): assert abs(sum(values[n+k*n:n+(k+1)*n])-1)<1e-12
        return values

def parse(path):
    pa=[x.split() for x in path.read_text().splitlines() if x.startswith('PA\t')][-1]
    groups=[]; g=0
    for term in pa[1].split('+'):
        a=list(map(int,term.split('*'))); repeats,width=(1,a[0]) if len(a)==1 else a
        for _ in range(repeats):groups.extend([g]*width);g+=1
    return list(map(float,pa[2:])),groups

if __name__=='__main__':
    import pathlib,json,sys
    case=sys.argv[1]; root=pathlib.Path('work/qualification/panel')/case
    s,groups=parse(root/'strict.out'); e,_=parse(root/'equivalent.out')
    out=pathlib.Path('work/pilot-surface'); points=[]
    for k in range(33):
        t=k/32; p=s if k==0 else e if k==32 else [math.exp(math.log(a)+t*(math.log(b)-math.log(a))) for a,b in zip(s,e)]
        points.append((f'path-{k}',p,50))
    rows=[json.loads(x) for x in (out/(case+'.jsonl')).read_text().splitlines()]
    for name,p in [('strict',s),('equivalent',e)]:
        points.append((name+'-80',p,80))
        coords=[x for x in rows if x['kind']=='coordinate' and x['base']==name and math.isfinite(x['ll'])]
        best=max(coords,key=lambda x:x['ll'])
        for label,j,d in [('lambda-minus1',3,-1),('lambda-plus1',3,1),('best-coordinate',best['index'],best['log_delta'])]:
            q=p.copy();q[j]*=math.exp(d);points.append((name+'-'+label,q,50))
    metadata=[]
    with (out/(case+'.matrices')).open('x') as f:
        for label,p,precision in points:
            v=model(p,groups,precision)
            f.write(label+' '+' '.join(map(repr,p+v))+'\n')
            metadata.append(dict(label=label,precision=precision,params=p))
    (out/(case+'.matrix-points.json')).write_text(json.dumps(metadata,indent=2)+'\n')
