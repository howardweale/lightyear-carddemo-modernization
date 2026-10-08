"""Create fresh proposals from a verified legacy ledger; leave old bytes untouched."""
import argparse,json
from pathlib import Path
from lightyear_factory.annotation_migration import propose

def main():
 p=argparse.ArgumentParser();p.add_argument('--ledger',type=Path,required=True);p.add_argument('--public-key',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();result=propose(a.ledger.read_bytes(),a.public_key.read_bytes())
 with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,sort_keys=True);f.write('\n')
 print(json.dumps(dict(proposals=len(result['proposals']),approval_transferred=False,model_calls=0)))
if __name__=='__main__':main()
