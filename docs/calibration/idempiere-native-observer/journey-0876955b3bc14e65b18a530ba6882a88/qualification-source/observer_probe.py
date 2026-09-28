"""Controlled native fixture for qualifying the observer, never a factory score."""
import json
import sys
import threading
import time
from .journey_worker import connect
from .native_catalog import query
from .contracts import require


def probe(lane,password):
    first=connect(lane,password);second=connect(lane,password)
    if lane=='postgresql':first.autocommit=False;second.autocommit=False
    errors=[];attempted=threading.Event();done=threading.Event()
    try:
        selected=query(first,'SELECT MIN(c_bpartner_id) id FROM adempiere.c_bpartner WHERE ad_client_id=11')[0]['id']
        require(type(selected) is int and selected>0,'Probe partner fixture missing')
        sql=f'UPDATE adempiere.c_bpartner SET so_creditlimit=so_creditlimit+1 WHERE c_bpartner_id={selected}'
        with first.cursor() as c:c.execute(sql)
        def waiter():
            try:
                attempted.set()
                with second.cursor() as c:c.execute(sql)
                time.sleep(.3);second.rollback();time.sleep(.5)
            except Exception as exc:errors.append(str(exc))
            finally:done.set()
        thread=threading.Thread(target=waiter,daemon=True);thread.start()
        require(attempted.wait(5),'Waiter did not start');time.sleep(1)
        first.rollback();time.sleep(.5)
        require(done.wait(10) and not errors,'Controlled lock probe failed')
        return {'fixture':'observer-only-controlled-lock-and-rollback','completed':True,
                'business_journey':False,'target_id':selected}
    finally:
        first.rollback();second.rollback();first.close();second.close()


if __name__=='__main__':
    spec=json.load(sys.stdin)
    try:print(json.dumps(probe(spec['lane'],spec['password'])))
    except Exception as exc:
        print(json.dumps({'error':str(exc).replace(spec['password'],'[redacted]')}));raise SystemExit(1)
