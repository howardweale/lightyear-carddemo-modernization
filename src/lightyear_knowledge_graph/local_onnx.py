"""Hash-pinned CPU sentence embeddings. No URL, download or remote-code path.

Token embeddings use attention-mask mean pooling and L2 normalization, as
specified by sentence-transformers/all-MiniLM-L6-v2. Model execution is opt-in;
the normal projection search remains keyword plus graph proximity.
"""
import hashlib
import json
from pathlib import Path
from lightyear_control_tower.decisions import digest


class LocalOnnxEmbedding:
    provider_id='local-onnx-mean-pooling'
    local=True

    def __init__(self,directory,manifest,*,session_factory=None,tokenizer_factory=None):
        root=Path(directory).resolve()
        if (manifest['schema']!='local-embedding-assets/1' or manifest['pooling']!='attention-mask-mean-l2' or
                manifest['max_tokens']!=256 or set(manifest['files'])!={'model.onnx','tokenizer.json'}):
            raise ValueError('embedding manifest')
        assets={}
        for name,expected in manifest['files'].items():
            path=root/name
            if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('embedding path')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('embedding asset hash')
            assets[name]=raw
        self.version=digest(manifest)
        if session_factory is None:
            import onnxruntime
            session_factory=lambda raw:onnxruntime.InferenceSession(raw,providers=['CPUExecutionProvider'])
        if tokenizer_factory is None:
            from tokenizers import Tokenizer
            tokenizer_factory=Tokenizer.from_str
        # Bytes, not a model pathname: ONNX external tensor files cannot be opened.
        self.session=session_factory(assets['model.onnx'])
        self.tokenizer=tokenizer_factory(assets['tokenizer.json'].decode())
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')

    def embed(self,texts):
        import numpy as np
        result=[]
        for offset in range(0,len(texts),32):
            encoded=self.tokenizer.encode_batch(texts[offset:offset+32])
            if not encoded:continue
            inputs=dict(input_ids=np.asarray([e.ids for e in encoded],dtype=np.int64),
                attention_mask=np.asarray([e.attention_mask for e in encoded],dtype=np.int64),
                token_type_ids=np.asarray([e.type_ids for e in encoded],dtype=np.int64))
            names={n.name for n in self.session.get_inputs()}
            if not names<={'input_ids','attention_mask','token_type_ids'} or 'attention_mask' not in names:
                raise ValueError('embedding model inputs')
            hidden=self.session.run(None,{k:v for k,v in inputs.items() if k in names})[0]
            if hidden.ndim!=3 or hidden.shape[:2]!=inputs['input_ids'].shape or not np.isfinite(hidden).all():
                raise ValueError('embedding model output')
            mask=inputs['attention_mask'][...,None]
            pooled=(hidden*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
            norm=np.linalg.norm(pooled,axis=1,keepdims=True)
            if (norm==0).any():raise ValueError('empty embedding')
            result.extend((pooled/norm).tolist())
        return result
