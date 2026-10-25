import importlib.util,json,pathlib,sys
root=pathlib.Path(sys.argv[sys.argv.index("--root")+1])
incoming=pathlib.Path(sys.argv[sys.argv.index("--incoming")+1])
record=pathlib.Path(sys.argv[sys.argv.index("--record")+1])
spec=importlib.util.spec_from_file_location("isolated_incoming",incoming/"scripts/experiments_tc2_gpu.py")
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
calls=[]
def host_preflight(*args,**kwargs):
    calls.append("host_preflight_stub_only")
    return {"status":"passed","offline_fixture":True,"model_calls":0}
module.preflight=host_preflight
value=module.publish(root,incoming,"B0",record)
assert calls == ["host_preflight_stub_only"]
print(json.dumps(value,sort_keys=True))
