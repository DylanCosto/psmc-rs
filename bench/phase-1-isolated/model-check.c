/* Synthetic differential fixture. See README.md for source/license provenance. */

#include <stdlib.h>
#include <stdio.h>
#include "psmc.h"
void out(double *x, int n) { fwrite(x, sizeof(double), n, stdout); }
int main(void) {
 int sizes[] = {1, 2, 4, 23, 64};
 srand48(42);
 for(int h=0;h<5;++h) for(int mode=0;mode<6;++mode) {
  int states=sizes[h]; psmc_par_t pp={0};
  pp.n=states-1; pp.n_free=(states+2)/3; pp.alpha=0.1; pp.tr_ratio=4.0; pp.max_t=15.0;
  pp.sum_n=23; pp.sum_L=177; pp.ran_init=(mode>=4)?0.1:0.0;
  pp.par_map=calloc(states,sizeof(int));
  for(int i=0;i<states;++i) pp.par_map[i]=i/3;
  if(mode%2) {pp.flag=PSMC_F_DIVERG; pp.dt0=0.7;}
  if(mode==2 || mode==3) {
   pp.inp_ti=calloc(states,sizeof(double));
   for(int i=0;i<states;++i) pp.inp_ti[i]=i*0.3;
  }
  psmc_data_t *pd=psmc_new_data(&pp);
  for(int update=0;update<2;++update) {
   out(pd->params,pd->n_params); out(pd->t,states+1); out(pd->sigma,states);
   out(&pd->C_pi,1); out(&pd->C_sigma,1); out(pd->hp->a0,states);
   for(int i=0;i<states;++i)out(pd->hp->a[i],states);
   for(int i=0;i<3;++i)out(pd->hp->e[i],states);
   double *avg=calloc(states,sizeof(double));psmc_avg_t(&pp,pd,avg);out(avg,states);free(avg);
   for(int i=0;i<pd->n_params;++i) pd->params[i]=pd->params[i]*(1.0+i*0.01);
   psmc_update_hmm(&pp,pd);
  }
  psmc_delete_data(pd);free(pp.par_map);free(pp.inp_ti);
 }
}
