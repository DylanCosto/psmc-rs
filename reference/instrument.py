#!/usr/bin/env python3
"""Make a separately instrumented copy of pinned lh3/psmc; never edit the input."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

PIN = "82fa2ada83ee463fe1251b562ae3d60e82d7ad6a"
HASHES = {
    "main.c": "3c229c0e8432a3e1a4a9de6f9fd69c2d89d1616661ee3c45862609614f15a356",
    "core.c": "aadc2135695e5139017f6636bf1001261e6702435800434de7e8db1a1b7969ae",
    "em.c": "57e738cbc2b56af453a3223615a56a0c15eefd9a5581031a7aa5ed2a0343acfd",
    "aux.c": "a155ed19359777e011891605a5880294d11b9ff9525aaef17dd9f4c606c8a012",
    "Makefile": "085225f4f2c4e694591f0c4d649df5bac4b2fe84b81e9e04c8eea2b37ad3fad7",
}

HEADER = r'''/* Additive test instrumentation. Upstream files and license are preserved. */
#ifndef PSMC_SNAPSHOT_H
#define PSMC_SNAPSHOT_H
#include "psmc.h"
enum { PSNP_FORWARD, PSNP_BACKWARD, PSNP_EXPECT, PSNP_MERGE, PSNP_MODEL,
       PSNP_Q, PSNP_MSTEP, PSNP_ALLOC, PSNP_LK, PSNP_PRE, PSNP_Q0, PSNP_FREE,
       PSNP_N_PHASES };
double psnp_now(void);
void psnp_elapsed(int phase, double start);
void psnp_seed(void);
void psnp_startup(const char *phase, double start);
void psnp_model(const psmc_par_t *pp, const psmc_data_t *pd);
void psnp_begin(void);
void psnp_sequence(int index, const psmc_seq_t *seq, const hmm_data_t *hd,
                   const hmm_exp_t *he, double ll);
void psnp_aggregate(const hmm_exp_t *he, double ll);
void psnp_objective(int count, int n, const double *raw, const psmc_data_t *pd, double result);
void psnp_end(const psmc_data_t *pd, int evaluations);
void psnp_draw(int source_index, int length, int accepted, long long before,
               long long after, long long target, int stop);
void psnp_bootstrap_end(int n, long long length, long long target);
#endif
'''

SOURCE = r'''/* Additive test instrumentation; original PSMC remains under LICENSE.txt. */
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "psmc_snapshot.h"

static FILE *snap, *profile, *trace;
static int initialized, iteration, model_id, draw_id;
static double durations[PSNP_N_PHASES], iteration_start, last_objective;
static const char *phase_names[PSNP_N_PHASES] = {
    "forward_seconds", "backward_seconds", "expectation_seconds", "expectation_merge_seconds",
    "model_seconds", "q_seconds", "m_step_seconds", "allocation_setup_seconds",
    "likelihood_seconds", "pre_backward_seconds", "q_normalizer_seconds", "free_seconds"
};

static FILE *open_env(const char *name)
{
    const char *path = getenv(name);
    FILE *fp;
    if (!path || !*path) return 0;
    fp = fopen(path, "w");
    if (!fp) { fprintf(stderr, "%s: %s: %s\n", name, path, strerror(errno)); exit(2); }
    return fp;
}
static void init(void)
{
    if (initialized) return;
    initialized = 1;
    snap = open_env("PSMC_SNAPSHOT");
    profile = open_env("PSMC_PROFILE");
    trace = open_env("PSMC_BOOTSTRAP_TRACE");
}
static void number(FILE *fp, double x)
{
    if (isnan(x)) fputs("\"nan\"", fp);
    else if (isinf(x)) fputs(x < 0 ? "\"-inf\"" : "\"inf\"", fp);
    else fprintf(fp, "%.17g", x);
}
static void string(FILE *fp, const char *s)
{
    const unsigned char *p = (const unsigned char*)s;
    fputc('"', fp);
    for (; *p; ++p) {
        if (*p == '"' || *p == '\\') { fputc('\\', fp); fputc(*p, fp); }
        else if (*p < 32 || *p >= 127) fprintf(fp, "\\u%04x", (unsigned)*p);
        else fputc(*p, fp);
    }
    fputc('"', fp);
}
static void vector(FILE *fp, const double *x, int n)
{
    int i;
    fputc('[', fp);
    for (i = 0; i < n; ++i) { if (i) fputc(',', fp); number(fp, x[i]); }
    fputc(']', fp);
}
static void matrix(FILE *fp, double **x, int rows, int cols)
{
    int i;
    fputc('[', fp);
    for (i = 0; i < rows; ++i) { if (i) fputc(',', fp); vector(fp, x[i], cols); }
    fputc(']', fp);
}
static void counts(FILE *fp, const hmm_exp_t *he)
{
    fputs(",\"A0\":", fp); vector(fp, he->A0, he->n);
    fputs(",\"A\":", fp); matrix(fp, he->A, he->n, he->n);
    fputs(",\"E\":", fp); matrix(fp, he->E, he->m+1, he->n);
    fputs(",\"stored_Q0\":", fp); number(fp, he->Q0);
}
double psnp_now(void)
{
    struct timespec t;
    init();
    if (!profile) return 0.0;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(2); }
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}
void psnp_elapsed(int phase, double start)
{
    if (profile) durations[phase] += psnp_now() - start;
}
void psnp_seed(void)
{
    const char *value = getenv("PSMC_SEED");
    char *end;
    long seed;
    init();
    if (!value || !*value) return;
    errno = 0;
    seed = strtol(value, &end, 10);
    if (errno || *end || end == value) { fprintf(stderr, "Invalid PSMC_SEED\n"); exit(2); }
    srand48(seed);
}
void psnp_startup(const char *phase, double start)
{
    if (!profile) return;
    fprintf(profile, "{\"event\":\"startup\",\"phase\":\"%s\",\"seconds\":%.17g}\n", phase, psnp_now()-start);
}
void psnp_model(const psmc_par_t *pp, const psmc_data_t *pd)
{
    int i;
    init();
    ++model_id;
    if (!snap) return;
    fprintf(snap, "{\"event\":\"model\",\"iteration\":%d,\"model_id\":%d,\"states\":%d,\"symbols\":%d,\"params\":",
            iteration, model_id, pd->hp->n, pd->hp->m);
    vector(snap, pd->params, pd->n_params);
    fputs(",\"par_map\":[", snap);
    for (i = 0; i <= pp->n; ++i) fprintf(snap, "%s%d", i ? "," : "", pp->par_map[i]);
    fputs("],\"t\":", snap); vector(snap, pd->t, pp->n+2);
    fputs(",\"initial\":", snap); vector(snap, pd->hp->a0, pd->hp->n);
    fputs(",\"transition\":", snap); matrix(snap, pd->hp->a, pd->hp->n, pd->hp->n);
    fputs(",\"emission\":", snap); matrix(snap, pd->hp->e, pd->hp->m+1, pd->hp->n);
    fputs(",\"sigma\":", snap); vector(snap, pd->sigma, pd->hp->n);
    fputs(",\"C_pi\":", snap); number(snap, pd->C_pi);
    fputs(",\"C_sigma\":", snap); number(snap, pd->C_sigma);
    fputs("}\n", snap);
}
void psnp_begin(void)
{
    ++iteration;
    memset(durations, 0, sizeof(durations));
    iteration_start = psnp_now();
    last_objective = NAN;
}
void psnp_sequence(int index, const psmc_seq_t *seq, const hmm_data_t *hd,
                   const hmm_exp_t *he, double ll)
{
    int i;
    if (!snap) return;
    fprintf(snap, "{\"event\":\"sequence\",\"iteration\":%d,\"model_id\":%d,\"index\":%d,\"name\":",
            iteration, model_id, index);
    string(snap, seq->name);
    fprintf(snap, ",\"length\":%d,\"observations\":[", hd->L);
    for (i = 1; i <= hd->L; ++i) fprintf(snap, "%s%d", i > 1 ? "," : "", (unsigned char)hd->seq[i]);
    fputs("],\"scales\":", snap); vector(snap, hd->s, hd->L+1);
    fputs(",\"forward\":", snap); matrix(snap, hd->f, hd->L+1, he->n);
    fputs(",\"backward\":", snap); matrix(snap, hd->b, hd->L+1, he->n);
    fputs(",\"log_likelihood\":", snap); number(snap, ll);
    counts(snap, he);
    fputs("}\n", snap);
}
void psnp_aggregate(const hmm_exp_t *he, double ll)
{
    if (!snap) return;
    fprintf(snap, "{\"event\":\"aggregate\",\"iteration\":%d,\"model_id\":%d,\"log_likelihood\":", iteration, model_id);
    number(snap, ll); counts(snap, he); fputs("}\n", snap);
}
void psnp_objective(int count, int n, const double *raw, const psmc_data_t *pd, double result)
{
    last_objective = result;
    if (!snap) return;
    fprintf(snap, "{\"event\":\"objective\",\"iteration\":%d,\"model_id\":%d,\"evaluation\":%d,\"raw_params\":",
            iteration, model_id, count);
    vector(snap, raw, n);
    fputs(",\"params\":", snap); vector(snap, pd->params, n);
    fputs(",\"negative_Q\":", snap); number(snap, result); fputs("}\n", snap);
}
void psnp_end(const psmc_data_t *pd, int evaluations)
{
    int i;
    if (snap) {
        fprintf(snap, "{\"event\":\"em_end\",\"iteration\":%d,\"model_id\":%d,\"optimizer_evaluations\":%d,\"params\":", iteration, model_id, evaluations);
        vector(snap, pd->params, pd->n_params);
        fputs(",\"Q0\":", snap); number(snap, pd->Q0);
        fputs(",\"Q1\":", snap); number(snap, pd->Q1);
        fputs(",\"last_candidate_Q\":", snap); number(snap, -last_objective);
        fputs(",\"log_likelihood\":", snap); number(snap, pd->lk);
        fputs(",\"post_sigma\":", snap); vector(snap, pd->post_sigma, pd->hp->n);
        fputs("}\n", snap); fflush(snap);
    }
    if (profile) {
        fprintf(profile, "{\"event\":\"em_profile\",\"iteration\":%d,\"optimizer_evaluations\":%d,\"total_seconds\":%.17g", iteration, evaluations, psnp_now()-iteration_start);
        for (i = 0; i < PSNP_N_PHASES; ++i) fprintf(profile, ",\"%s\":%.17g", phase_names[i], durations[i]);
        fputs("}\n", profile); fflush(profile);
    }
}
void psnp_draw(int source_index, int length, int accepted, long long before,
               long long after, long long target, int stop)
{
    if (!trace) return;
    fprintf(trace, "{\"event\":\"bootstrap_draw\",\"draw\":%d,\"source_index\":%d,\"length\":%d,\"accepted\":%s,\"before_length\":%lld,\"after_length\":%lld,\"target_length\":%lld,\"stop\":%s}\n",
            draw_id++, source_index, length, accepted ? "true" : "false", before, after, target, stop ? "true" : "false");
}
void psnp_bootstrap_end(int n, long long length, long long target)
{
    if (!trace) return;
    fprintf(trace, "{\"event\":\"bootstrap_end\",\"accepted_sequences\":%d,\"length\":%lld,\"target_length\":%lld}\n", n, length, target);
    fflush(trace);
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source anchor, found {text.count(old)}: {old[:100]!r}")
    return text.replace(old, new, 1)


def transform(name, text):
    def change(old, new):
        nonlocal text
        text = replace_once(text, old, new)
    if name != "Makefile":
        change('#include "psmc.h"', '#include "psmc.h"\n#include "psmc_snapshot.h"')
    if name == "main.c":
        change('\tint i;', '\tint i;\n\tdouble psnp_start;')
        change('\tsrand48(time(0) ^ getpid());', '\tsrand48(time(0) ^ getpid());\n\tpsnp_seed();\n\tpsnp_start = psnp_now();')
        change('\tpp = psmc_parse_cli(argc, argv);', '\tpp = psmc_parse_cli(argc, argv);\n\tpsnp_startup("cli_input_bootstrap", psnp_start);\n\tpsnp_start = psnp_now();')
        change('\tpd = psmc_new_data(pp);', '\tpd = psmc_new_data(pp);\n\tpsnp_startup("initial_model", psnp_start);')
    elif name == "core.c":
        change('\tt = pd->t;\n\tlambda =', '\tdouble psnp_start = psnp_now();\n\tt = pd->t;\n\tlambda =')
        change('\tfree(q); free(alpha); free(beta); free(q_aux); free(lambda); free(tau);', '\tfree(q); free(alpha); free(beta); free(q_aux); free(lambda); free(tau);\n\tpsnp_elapsed(PSNP_MODEL, psnp_start);\n\tpsnp_model(pp, pd);')
    elif name == "em.c":
        change('\treturn -hmm_Q(aux->pd->hp, aux->he);', '\t{\n\t\tdouble psnp_start = psnp_now();\n\t\tdouble result = -hmm_Q(aux->pd->hp, aux->he);\n\t\tpsnp_elapsed(PSNP_Q, psnp_start);\n\t\tpsnp_objective(aux->cnt, n, params, aux->pd, result);\n\t\treturn result;\n\t}')
        change('\tdouble LL = 0.0;', '\tdouble LL = 0.0;\n\tdouble psnp_start;\n\tint psnp_evaluations = 0;\n\tpsnp_begin();\n\tpsnp_start = psnp_now();')
        change('\the_sum = hmm_new_exp(hp);\n\thmm_pre_backward(hp);', '\the_sum = hmm_new_exp(hp);\n\tpsnp_elapsed(PSNP_ALLOC, psnp_start);\n\tpsnp_start = psnp_now();\n\thmm_pre_backward(hp);\n\tpsnp_elapsed(PSNP_PRE, psnp_start);')
        change('\t\tchar *seq;', '\t\tchar *seq;\n\t\tdouble psnp_ll;\n\t\tpsnp_start = psnp_now();')
        change('\t\thd = hmm_new_data(s->L, seq, hp);', '\t\thd = hmm_new_data(s->L, seq, hp);\n\t\tpsnp_elapsed(PSNP_ALLOC, psnp_start);')
        change('\t\thmm_forward(hp, hd);\n\t\thmm_backward(hp, hd);\n\t\tLL += hmm_lk(hd);\n\t\the = hmm_expect(hp, hd);\n\t\thmm_add_expect(he, he_sum);',
'''\t\tpsnp_start = psnp_now();
\t\thmm_forward(hp, hd);
\t\tpsnp_elapsed(PSNP_FORWARD, psnp_start);
\t\tpsnp_start = psnp_now();
\t\thmm_backward(hp, hd);
\t\tpsnp_elapsed(PSNP_BACKWARD, psnp_start);
\t\tpsnp_start = psnp_now();
\t\tpsnp_ll = hmm_lk(hd);
\t\tLL += psnp_ll;
\t\tpsnp_elapsed(PSNP_LK, psnp_start);
\t\tpsnp_start = psnp_now();
\t\the = hmm_expect(hp, hd);
\t\tpsnp_elapsed(PSNP_EXPECT, psnp_start);
\t\tpsnp_sequence(i, s, hd, he, psnp_ll);
\t\tpsnp_start = psnp_now();
\t\thmm_add_expect(he, he_sum);
\t\tpsnp_elapsed(PSNP_MERGE, psnp_start);''')
        change('\t\t// free\n\t\thmm_delete_exp(he);', '\t\t// free\n\t\tpsnp_start = psnp_now();\n\t\thmm_delete_exp(he);')
        change('\t\tfree(seq);', '\t\tfree(seq);\n\t\tpsnp_elapsed(PSNP_FREE, psnp_start);')
        change('\t\tem_aux_t aux;\n\t\thmm_Q0(hp, he_sum);', '\t\tem_aux_t aux;\n\t\tdouble psnp_mstep_start = psnp_now();\n\t\tpsnp_start = psnp_now();\n\t\thmm_Q0(hp, he_sum);\n\t\tpsnp_elapsed(PSNP_Q0, psnp_start);\n\t\tpsnp_aggregate(he_sum, LL);')
        change('\t\tpd->Q0 = hmm_Q(hp, he_sum);', '\t\tpsnp_start = psnp_now();\n\t\tpd->Q0 = hmm_Q(hp, he_sum);\n\t\tpsnp_elapsed(PSNP_Q, psnp_start);')
        change('\t\tfree(params);', '\t\tpsnp_evaluations = aux.cnt;\n\t\tfree(params);\n\t\tpsnp_elapsed(PSNP_MSTEP, psnp_mstep_start);')
        change('\thmm_delete_exp(he_sum);\n\treturn pd->Q1;', '\tpsnp_start = psnp_now();\n\thmm_delete_exp(he_sum);\n\tpsnp_elapsed(PSNP_FREE, psnp_start);\n\tpsnp_end(pd, psnp_evaluations);\n\treturn pd->Q1;')
    elif name == "aux.c":
        change('\t\tint tmp2 = L + s->L - L_ori;', '\t\tint tmp2 = L + s->L - L_ori;\n\t\tint64_t psnp_before = L;')
        change('\t\tif (tmp1 >= 0 && tmp2 >= 0) break;', '\t\tpsnp_draw((int)(s - pp->seqs), s->L, tmp2 <= 0 || (tmp2 > 0 && tmp1 > 0 && tmp2 < tmp1), psnp_before, L, L_ori, tmp1 >= 0 && tmp2 >= 0);\n\t\tif (tmp1 >= 0 && tmp2 >= 0) break;')
        change('\t// delete old information', '\tpsnp_bootstrap_end(n_seqs, L, L_ori);\n\t// delete old information')
    elif name == "Makefile":
        change('OBJS=\t\tkhmm.o kmin.o cli.o core.o em.o aux.o', 'OBJS=\t\tkhmm.o kmin.o cli.o core.o em.o aux.o psmc_snapshot.o')
        text += '\nmain.o core.o em.o aux.o psmc_snapshot.o:psmc_snapshot.h\n'
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    src, dst = args.source.resolve(), args.destination.resolve()
    if dst.exists() or dst == src or src in dst.parents:
        parser.error("destination must not exist and must not be inside source")
    transformed = {}
    for name, expected in HASHES.items():
        raw = (src / name).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            parser.error(f"{name} differs from pinned source {PIN}: {actual}")
        transformed[name] = transform(name, raw.decode())
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "*.o", "psmc"))
    for name, content in transformed.items():
        (dst / name).write_text(content)
    (dst / "psmc_snapshot.h").write_text(HEADER)
    (dst / "psmc_snapshot.c").write_text(SOURCE)
    manifest = {
        "source_commit": PIN,
        "original_source_sha256": HASHES,
        "transformed_sha256": {name: hashlib.sha256((dst / name).read_bytes()).hexdigest()
                               for name in [*HASHES, "psmc_snapshot.h", "psmc_snapshot.c"]},
        "instrumenter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (dst / "instrumentation-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"source_commit": PIN, "destination": str(dst), "files_transformed": list(HASHES)}))


if __name__ == "__main__":
    main()
