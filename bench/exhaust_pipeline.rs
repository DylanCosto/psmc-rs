// Experimental one-record lookahead. CPU messages of the next original record
// overlap outstanding transition counts. All aggregate additions stay in order.
impl CudaBackend {
    fn pipelined(&mut self, model: &Model, sequences: &[&Sequence]) -> io::Result<(Counts,f64)> {
        let prepared=self.workspace.prepare(model);
        let ae=psmc_core::hmm::pre_backward(model);
        self.device.prepare(&ae).map_err(io::Error::other)?;
        self.device.set_deferred(true);
        self.counters.cuda_upload_bytes+=(ae.len()*8) as u64;
        let mut occurrences=HashMap::<&[u8],usize>::new();
        if self.cache_enabled {for sequence in sequences {*occurrences.entry(&sequence.observations).or_default()+=1;}}
        let mut cache=HashMap::<&[u8],Cached>::new();
        let mut pending:Option<(&[u8],Cached,bool)>=None;
        let mut aggregate=Counts::zero(model.n);
        let mut likelihood=0.0;
        fn flush<'a>(device:&mut driver::Device,pending:&mut Option<(&'a [u8],Cached,bool)>,cache:&mut HashMap<&'a [u8],Cached>,occurrences:&HashMap<&[u8],usize>,aggregate:&mut Counts,likelihood:&mut f64)->io::Result<()> {
            if let Some((obs,mut saved,launched))=pending.take() {
                if launched {device.finish(&mut saved.counts.a).map_err(io::Error::other)?;}
                warn(saved.backward_check);
                *likelihood+=saved.likelihood;
                aggregate.add(&saved.counts);
                if occurrences.get(obs).is_some_and(|&n|n>1) {cache.insert(obs,saved);}
            }
            Ok(())
        }
        for sequence in sequences {
            let obs=sequence.observations.as_slice();
            self.counters.sequence_visits+=1;
            if cache.contains_key(obs) || pending.as_ref().is_some_and(|p|p.0==obs) {
                flush(&mut self.device,&mut pending,&mut cache,&occurrences,&mut aggregate,&mut likelihood)?;
            }
            if let Some(saved)=cache.get(obs) {
                warn(saved.backward_check);likelihood+=saved.likelihood;aggregate.add(&saved.counts);self.counters.cache_hits+=1;continue;
            }
            // This CPU work is independent of the pending record's GPU counts.
            let (messages,counts)=self.workspace.evaluate_without_transitions(&prepared,obs);
            let mut saved=Cached {counts:counts.clone(),likelihood:messages.log_likelihood,backward_check:messages.backward_check};
            flush(&mut self.device,&mut pending,&mut cache,&occurrences,&mut aggregate,&mut likelihood)?;
            for start in (1..obs.len()).step_by(self.tile_sites) {
                let end=(start+self.tile_sites).min(obs.len());
                self.device.tile(&messages.forward[start*model.n..end*model.n],&messages.backward[(start+1)*model.n..(end+1)*model.n],&obs[start..end],&mut saved.counts.a,model.n,start==1,end==obs.len()).map_err(io::Error::other)?;
                self.counters.cuda_launches+=1;
                self.counters.cuda_upload_bytes+=((end-start)*(16*model.n+1)) as u64;
                if end==obs.len() {self.counters.cuda_download_bytes+=(8*model.n*model.n) as u64;}
            }
            self.counters.sequence_evaluations+=1;
            pending=Some((obs,saved,obs.len()>1));
        }
        flush(&mut self.device,&mut pending,&mut cache,&occurrences,&mut aggregate,&mut likelihood)?;
        self.device.set_deferred(false);
        Ok((aggregate,likelihood))
    }
}
