#!/usr/bin/env python3
"""Source-derived structured algebra counterexample; no production modifications."""
import json
import math
import struct
from pathlib import Path
import os
from common import ROOT, save, sha256
from phase3_common import resource_policy


def bits(x): return struct.pack('d',x)


def compare(expected, actual):
    diffs=[(i,a,b) for i,(a,b) in enumerate(zip(expected,actual)) if bits(a)!=bits(b)]
    return dict(values=len(expected),bit_mismatches=len(diffs),maximum_absolute_error=max([abs(a-b) for _,a,b in diffs] or [0]),
                maximum_relative_error=max([abs(a-b)/max(abs(a),abs(b),1e-300) for _,a,b in diffs] or [0]),
                first_mismatches=[dict(index=i,expected=a,actual=b) for i,a,b in diffs[:8]])


def main():
    os.chdir(ROOT)
    policy=resource_policy()
    path=Path('tests/fixtures/cpu-campaign-hmm/generating-model.jsonl')
    model,=[json.loads(s) for s in path.read_text().splitlines() if json.loads(s)['event']=='model']
    n=model['states']
    rho=model['params'][1]
    lam=[model['params'][3+g] for g in model['par_map']]
    tau=[model['t'][i+1]-model['t'][i] for i in range(n)]
    alpha=[1.0]+[0.0]*n
    beta=[0.0]*n
    for k in range(1,n): alpha[k]=alpha[k-1]*math.exp(-tau[k-1]/lam[k-1])
    for k in range(1,n): beta[k]=beta[k-1]+lam[k-1]*(1.0/alpha[k]-1.0/alpha[k-1])
    aux=[(alpha[k]-alpha[k+1])*(beta[k]-lam[k]/alpha[k])+tau[k] for k in range(n-1)]
    cpi=0.0
    for k in range(n): cpi+=lam[k]*(alpha[k]-alpha[k+1])
    csigma=1.0/(cpi*rho)+0.5
    assert bits(cpi)==bits(model['C_pi']) and bits(csigma)==bits(model['C_sigma'])
    matrix=model['transition']
    literal=[]
    factored=[]
    lower=[]
    upper=[]
    delta=[alpha[k]-alpha[k+1] for k in range(n)]
    running_time=0.0
    for k in range(n):
        ak1=delta[k]
        cpik=ak1*(running_time+lam[k])-alpha[k+1]*tau[k]
        pik=cpik/cpi
        sigma=(ak1/(cpi*rho)+pik/2.0)/csigma
        assert bits(sigma)==bits(model['sigma'][k])
        rate=pik/(csigma*sigma)
        lower.append(rate*(ak1/cpik))
        upper.append(rate*(aux[k]/cpik) if k<n-1 else 0.0)
        row=[]
        candidate=[]
        for l in range(n):
            if l<k:
                q=(ak1/cpik)*aux[l]
                row.append(rate*q)
                candidate.append(lower[k]*aux[l])
            elif l==k:
                q=(ak1*ak1*(beta[k]-lam[k]/alpha[k])+2.0*lam[k]*ak1-2.0*alpha[k+1]*tau[k])/cpik
                row.append(rate*q+(1.0-rate))
                candidate.append(matrix[k][k])
            else:
                q=delta[l]*(aux[k]/cpik)
                row.append(rate*q)
                candidate.append(upper[k]*delta[l])
        literal.extend(row)
        factored.extend(candidate)
        running_time+=tau[k]
    expected=[v for row in matrix for v in row]
    literal_check=compare(expected,literal)
    assert literal_check['bit_mismatches']==0,'Literal reconstruction must match C before assessing a rewrite'
    reconstruction=compare(expected,factored)
    vectors=[]
    for name,values in [('uniform',[1.0]*n),('initial',model['initial']),('uneven',[1.0+(i*7)%13 for i in range(n)])]:
        total=0.0
        for value in values: total+=value
        f=[v/total for v in values]
        dense=[]
        for k in range(n):
            total=0.0
            for l in range(n): total+=f[l]*matrix[l][k]
            dense.append(model['emission'][0][k]*total)
        prefix=[0.0]*n
        suffix=[0.0]*n
        running=0.0
        for k in range(n):
            prefix[k]=running
            running+=f[k]*upper[k]
        running=0.0
        for k in range(n-1,-1,-1):
            suffix[k]=running
            running+=f[k]*lower[k]
        candidate=[model['emission'][0][k]*(delta[k]*prefix[k]+f[k]*matrix[k][k]+(aux[k]*suffix[k] if k<n-1 else 0.0)) for k in range(n)]
        vectors.append(dict(name=name,**compare(dense,candidate)))
    # Arbitrary positive full counts suffice to test the claimed Q identity.
    # Both calculations include identical emission terms and the same Q0.
    counts=[[(k*n+l+1)*1e-5 for l in range(n)] for k in range(n)]
    emission_sum=0.0
    for b in range(2):
        for k in range(n): emission_sum+=(k+1)*0.01*math.log(model['emission'][b][k])
    q0=0.0
    for k in range(n):
        e=(k+1)*0.01
        tmp=0.0
        for _ in range(2): tmp+=e
        for _ in range(2): q0+=e*math.log(e/tmp)
    for k in range(n):
        tmp=0.0
        for l in range(n): tmp+=counts[k][l]
        for l in range(n): q0+=counts[k][l]*math.log(counts[k][l]/tmp)
    dense=emission_sum
    for k in range(n):
        for l in range(n): dense+=counts[k][l]*math.log(matrix[k][l])
    dense-=q0
    # Per-row and per-column triangular margins, each accumulated in ascending order.
    lr=[0.0]*n; lc=[0.0]*n; ur=[0.0]*n; uc=[0.0]*n
    for k in range(n):
        for l in range(n):
            if l<k: lr[k]+=counts[k][l]; lc[l]+=counts[k][l]
            elif l>k: ur[k]+=counts[k][l]; uc[l]+=counts[k][l]
    candidate=emission_sum
    for k in range(n):
        candidate+=counts[k][k]*math.log(matrix[k][k])
        if k>0: candidate+=lr[k]*math.log(lower[k])
        if k<n-1: candidate+=lc[k]*math.log(aux[k])
        if k<n-1: candidate+=ur[k]*math.log(upper[k])
        if k>0: candidate+=uc[k]*math.log(delta[k])
    candidate-=q0
    objective=compare([dense],[candidate])
    assert reconstruction['bit_mismatches']>0 or any(v['bit_mismatches'] for v in vectors) or objective['bit_mismatches']>0
    save('bench/cpu-campaign-algebra.json',dict(status='strict_counterexample_confirmed',resource_policy=policy,
         source='Pinned core.c::psmc_update_hmm and khmm.c::hmm_Q', model_snapshot=str(path),model_sha256=sha256(path),
         states=n,literal_reconstruction=literal_check,factored_reconstruction=reconstruction,
         forward_vectors=vectors,factored_objective=objective,runner_sha256=sha256(__file__),
         conclusion='This direct factor/prefix/suffix/log-margin rewrite is not strict-compatible even at a valid initial model. It remains an isolated experiment, not a production backend.',
         limitations=['One valid model counterexample disproves universal exactness of this formulation; it does not rule out all future strict algorithms.',
                     'No full EM run, optimizer-trajectory or speed claim for the failed strict candidate.',
                     'The real-arithmetic identity is distinct from operation-order-preserving binary64 computation.']))
    print(json.dumps(dict(reconstruction_mismatches=reconstruction['bit_mismatches'],forward_mismatches=[v['bit_mismatches'] for v in vectors],q_mismatches=objective['bit_mismatches'])))


if __name__=='__main__': main()
