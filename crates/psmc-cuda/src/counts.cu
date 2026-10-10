// Ordered binary64 translation of khmm.c hmm_expect; original MIT notice is
// retained in reference/LICENSE.psmc.txt. One thread owns one transition cell.
extern "C" __global__ void counts(const double* f, const double* b,
    const unsigned char* obs, const double* ae, double* a,
    int n, int sites, int reset) {
    int cell = blockIdx.x * blockDim.x + threadIdx.x;
    if (cell >= n*n) return;
    int k = cell / n, l = cell % n;
    double a0 = ae[cell], a1 = ae[n*n+cell], a2 = ae[2*n*n+cell];
    double sum = reset ? 1e-25 : a[cell];
    for (int u=0; u<sites; ++u) {
        double coefficient = obs[u]==0 ? a0 : (obs[u]==1 ? a1 : a2);
        double product = __dmul_rn(f[(long long)u*n+k], coefficient);
        sum = __dadd_rn(sum, __dmul_rn(product, b[(long long)u*n+l]));
    }
    a[cell] = sum;
}
