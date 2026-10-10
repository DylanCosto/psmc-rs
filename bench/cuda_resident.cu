// Experimental ordered messages, not linked into the production CUDA backend.
// Each computational tile carries its true HMM boundary through global memory.
extern "C" __global__ void forward(const double* initial,const double* a,
 const double* e,const unsigned char* obs,double* f,double* scales,int n,int start,int end) {
 __shared__ double prev[128],cur[128],sum;
 int k=threadIdx.x;
 if(k<n) prev[k]=start==1 ? 0.0 : f[(long long)(start-1)*n+k];
 __syncthreads();
 for(int u=start;u<end;++u) {
  if(k<n) {
   double x=0.0;
   if(u==1) x=__dmul_rn(initial[k],e[(int)obs[0]*n+k]);
   else {
    for(int l=0;l<n;++l) x=__dadd_rn(x,__dmul_rn(prev[l],a[l*n+k]));
    x=__dmul_rn(e[(int)obs[u-1]*n+k],x);
   }
   cur[k]=x;
  }
  __syncthreads();
  if(k==0) {double x=0.0;for(int l=0;l<n;++l)x=__dadd_rn(x,cur[l]);sum=x;scales[u]=x;}
  __syncthreads();
  if(k<n) {prev[k]=__ddiv_rn(cur[k],sum);f[(long long)u*n+k]=prev[k];}
  __syncthreads();
 }
}
extern "C" __global__ void backward(const double* ae,const unsigned char* obs,
 const double* scales,double* b,int n,int length,int start,int end) {
 __shared__ double next[128],cur[128];int k=threadIdx.x;
 if(k<n) next[k]=start==length ? 0.0 : b[(long long)(start+1)*n+k];
 __syncthreads();
 for(int u=start;u>=end;--u) {
  if(k<n) {
   double x=0.0;
   if(u==length) x=__ddiv_rn(1.0,scales[u]);
   else {
    for(int l=0;l<n;++l) x=__dadd_rn(x,__dmul_rn(ae[((int)obs[u]*n+k)*n+l],next[l]));
    x=__ddiv_rn(x,scales[u]);
   }
   cur[k]=x;b[(long long)u*n+k]=x;
  }
  __syncthreads();if(k<n)next[k]=cur[k];__syncthreads();
 }
}
