"""Approved toolkit and paging regressions for PR B."""
from tests.verify_graph_support import *
from lightyear_toolkit.graph import GraphTools


class ToolkitGraphTests(GraphFixture):
    def tools(self, mode="field", **kw):
        m=self.build(mode=mode,**kw)
        p=read(self.out/"projection.json.gz")
        return GraphTools(p,m,{"review_after":"2099-01-01"},self.root,
            Mock(call=Mock(return_value={"ok":True,"diagnostics":[]}))),m


    def test_public_fixture_determinism_and_field_references(self):
        graph,m=self.tools()
        self.build(out=self.root/"same")
        for name in ("projection.json.gz","projection-manifest.json"):
            self.assertEqual((self.out/name).read_bytes(),(self.root/"same"/name).read_bytes())
        nodes=graph.call("graph_search",query="ACCT-CURR-BAL")["items"]
        self.assertTrue(nodes)
        refs=graph.call("graph_references",node_id=nodes[0]["id"])["items"]
        self.assertTrue(any("CBACT04C" in r["id"] and r["kind"]=="cobol_paragraph" for r in refs))
        self.assertNotIn("inspector_private",(gzip.decompress((self.out/"projection.json.gz").read_bytes())).decode())
        with self.assertRaises(ValueError): self.build()


    def test_confidential_bytes_independent_of_watch_and_no_publication_loading(self):
        self.build(mode="confidential",watch={"FIRST-PRIVATE-TOKEN"})
        self.build(mode="confidential",watch={"OTHER-PRIVATE-TOKEN"},out=self.root/"other")
        self.assertEqual((self.out/"projection.json.gz").read_bytes(),(self.root/"other/projection.json.gz").read_bytes())
        with patch("lightyear_knowledge_graph.explorer.load_publication",side_effect=AssertionError("source access")):
            GraphTools(read(self.out/"projection.json.gz"),read(self.out/"projection-manifest.json"),
                       {"review_after":"2099-01-01"},self.root,Mock())


    def test_budgets_cursor_scope_and_all_results(self):
        graph,_=self.tools()
        # Expand only the in-memory synthetic public fixture beyond the explorer's old 100 limit.
        proto=copy.deepcopy(graph.payload["nodes"][0])
        nodes=[{**proto,"id":"fixture:"+str(i),"name":"searchable-"+str(i)} for i in range(215)]
        graph.payload={**graph.payload,"nodes":nodes,"edges":[]}
        from lightyear_knowledge_graph.explorer import GraphExplorerIndex
        graph.index=GraphExplorerIndex(graph.payload,ontology={"relations":{}},projection_only=True)
        cursor=""; found=[]
        while True:
            r=graph.call("graph_search",query="searchable",limit=25,cursor=cursor)
            self.assertLessEqual(len(canonical(r)),8192)
            found.extend(n["id"] for n in r["items"])
            cursor=r["cursor"]
            if not cursor: break
            self.assertTrue(r["truncated"])
            wrong=graph.call("graph_search",query="different",cursor=cursor)
            self.assertIn("error",wrong)
        self.assertEqual(215,len(set(found)))
        huge=graph.index.node_by_id[nodes[0]["id"]]
        huge["properties"]["statement"]="x"*100000
        r=graph.call("graph_node",node_id=huge["id"])
        self.assertTrue(r["truncated"]); self.assertLessEqual(len(canonical(r)),8192)


    def test_explain_uses_only_visible_field_or_dataset(self):
        graph,_=self.tools()
        graph.client.call.return_value={"ok":True,"diagnostics":[{"dataset":"STEP15/ACCTFILE","field":"ACCT-CURR-BAL","value":"MUST-NOT-LEAK"}]}
        r=graph.call("explain_divergence",attempt_id="fixture")
        self.assertTrue(any(n["kind"]=="cobol_field" for n in r["items"]))
        self.assertNotIn("MUST-NOT-LEAK",json.dumps(r))
        graph.payload["mode"]="confidential"
        r=graph.call("explain_divergence",attempt_id="fixture")
        self.assertTrue(any(n["kind"]=="copybook" for n in r["items"]))
        self.assertFalse(any(n["kind"]=="cobol_field" for n in r["items"]))
        graph.decision["review_after"]="2020-01-01"
        self.assertIn("error",graph.call("graph_search",query="ACCT"))


    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Optional MCP SDK")
    def test_default_tools_schemas_and_optional_registration(self):
        from lightyear_toolkit.mcp import create_server
        server=create_server(Mock(),Mock())
        tools=asyncio.run(server.list_tools())
        self.assertEqual(10,len(tools))
        current=[{k:v for k,v in t.model_dump(by_alias=True).items() if k in ("name","inputSchema")} for t in tools]
        self.assertEqual(read(ROOT/"tests/verify_tools_baseline.json"),current)
        decode=next(t for t in tools if t.name=="decode_records")
        self.assertEqual({"path","copybook","codec","framing"},set(decode.input_schema["properties"]) if hasattr(decode,"input_schema") else set(decode.inputSchema["properties"]))
        graph,_=self.tools()
        on=asyncio.run(create_server(Mock(),Mock(),graph).list_tools())
        self.assertEqual(16,len(on))
        for t in on:
            if t.name.startswith("graph_") or t.name=="explain_divergence":
                self.assertTrue(t.annotations.read_only_hint if hasattr(t.annotations,"read_only_hint") else t.annotations.readOnlyHint)
        expiring=create_server(Mock(),Mock(),graph)
        graph.decision["review_after"]="2020-01-01"
        expired=asyncio.run(expiring.list_tools())
        self.assertEqual(current,[{k:v for k,v in t.model_dump(by_alias=True).items() if k in ("name","inputSchema")} for t in expired])


    def test_decode_paging_fields_and_summary_on_public_fixture(self):
        from lightyear_toolkit.workspace import Workspace
        cp=ROOT/"spec/mainframe/copybooks/CVACT01Y.cpy"
        binary=ROOT/"tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05/before/ACCTFILE.bin"
        (self.root/"account.cpy").write_bytes(cp.read_bytes());(self.root/"accounts.bin").write_bytes(binary.read_bytes())
        ws=Workspace(self.root,{"account.cpy":{"purpose":"copybook","sha256":sha(cp.read_bytes())},
            "accounts.bin":{"purpose":"development-records","sha256":sha(binary.read_bytes()),"copybook":"account.cpy"}})
        old=ws.decode("accounts.bin","account.cpy","cp037","fixed")
        field=old["records"][0]["fields"][0]["path"]
        page=ws.decode_page("accounts.bin","account.cpy",limit=1,fields=[field])
        self.assertEqual(1,len(page["records"])); self.assertEqual([field],[f["path"] for f in page["records"][0]["fields"]])
        summary=ws.decode_page("accounts.bin","account.cpy",fields=[field],summary=True)
        self.assertEqual(len(old["records"]),summary["summary"][field]["count"])
        for kw in (dict(limit=201),dict(offset=-1),dict(fields=["not-a-field"])):
            with self.assertRaises(ValueError): ws.decode_page("accounts.bin","account.cpy",**kw)


    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Optional MCP SDK")
    def test_startup_falls_back_to_original_tools_once_and_validates_judge_context(self):
        from lightyear_toolkit import mcp
        from mcp.server import MCPServer
        m=self.build(); leak_check(self.out,digest(self.lane),set(),self.signer,evaluation_inventory_sha256=digest({}))
        proof,trust=self.approve(m)
        config=self.root/"public.json";config.write_bytes(canonical({"files":{},"graph_trust":trust}))
        decision=self.root/"proof.json";decision.write_bytes(canonical(proof))
        client=Mock()
        client.call.return_value=dict(ok=True,context_projection_sha256=m["projection_sha256"],
            context_lane_sha256=m["lane_sha256"],disclosure_mode="field")
        observed=[]
        def no_serve(server,**kwargs):
            observed.append(len(asyncio.run(server.list_tools())))
        args=["--workspace",str(self.root),"--public-manifest",str(config),"--judge-url","http://127.0.0.1:1"]
        with patch.object(mcp,"JudgeClient",return_value=client),patch.object(MCPServer,"run",new=no_serve),patch.dict(os.environ,LIGHTYEAR_VERIFY_TOKEN="fixture"):
            mcp.main(args+["--graph-projection",str(self.out),"--graph-decision",str(decision)])
            self.assertEqual(16,observed[-1])
            client.call.return_value["context_projection_sha256"]="f"*64
            log=io.StringIO()
            with redirect_stderr(log):
                mcp.main(args+["--graph-projection",str(self.out),"--graph-decision",str(decision)])
            self.assertEqual(10,observed[-1]);self.assertEqual(1,len(log.getvalue().splitlines()))
            with redirect_stderr(io.StringIO()):
                mcp.main(args+["--graph-projection",str(self.out)])
            self.assertEqual(10,observed[-1])
