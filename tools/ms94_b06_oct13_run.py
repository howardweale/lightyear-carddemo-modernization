"""Explicit Oct13 entry point. Building or importing never authorizes execution."""
import argparse
import sys
from tools.ms94_b06_oct13_authorization import authorized

def main():
    parser=argparse.ArgumentParser(description=__doc__,add_help=False)
    parser.add_argument('--go',required=True);parser.add_argument('--request',required=True)
    parser.add_argument('--request-file-sha256',required=True);parser.add_argument('--worker',action='store_true')
    args,remaining=parser.parse_known_args()
    with authorized(args.request,args.request_file_sha256,args.go):
        previous=sys.argv
        sys.argv=[previous[0],*remaining,'--approval',args.request,'--approved-sha256',args.request_file_sha256]
        try:
            if args.worker:
                from tools.ms94_b06_engineering_worker import main as run
            else:
                from tools.ms94_b06_engineering_run import main as run
            run()
        finally:sys.argv=previous
if __name__=='__main__':main()
