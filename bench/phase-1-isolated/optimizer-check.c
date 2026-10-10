/* Synthetic differential fixture. See README.md for source/license provenance. */

#include <stdio.h>
#include <math.h>
#include "kmin.h"
void out(double *x, int n) {fwrite(x,sizeof(double),n,stdout);}
double objective(int n,double *x,void *data) {
 int mode=*(int*)data;out(x,n);double sum=0.0;
 if(mode==1)return 7.0;
 if(mode==2 && x[0] > 0.1)return NAN;
 if(mode==3)return x[0];
 for(int i=0;i<n;++i) sum+=(x[i]-i)*(x[i]-i);
 return sum;
}
int main(void){for(int mode=0;mode<4;++mode)for(int limit=1;limit<=1000;limit*=10){double x[]={0.0,1.0,-2.0};double r=kmin_hj(objective,3,x,&mode,0.5,1e-7,limit);out(x,3);out(&r,1);}}
