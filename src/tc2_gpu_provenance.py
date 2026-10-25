"""Current-source contracts and read-only historical ZIP provenance; no tensor imports."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import zipfile

CONFIG_ROLES=("protocol","workflow","setup","runtime","pilot","experiments","analysis","figure_revision")
_INDEX_CACHE={}
_ARCHIVE_CACHE={}

def _root(root):
    value=str(Path(root).absolute())
    if value.startswith("\\\\?\\"):value=value[4:]
    return Path(value).resolve()

def _relative(name):
    if not isinstance(name,str) or not name or "\\" in name or ":" in name:
        raise ValueError("Expected a repository-relative POSIX path")
    path=PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix()!=name or name==".":
        raise ValueError("Unsafe provenance path")
    return name

def _inside(root,name):
    root=_root(root);path=root/_relative(name)
    for node in (path,*path.parents):
        if node==root.parent:break
        if node.exists() and (node.is_symlink() or getattr(node.lstat(),"st_file_attributes",0)&1024):
            raise ValueError("Links and reparse points are not permitted in provenance paths")
    if not path.resolve().is_relative_to(root):raise ValueError("Provenance path escapes repository")
    return path

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024**2),b""):h.update(block)
    return h.hexdigest().upper()

def _decode(data):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError("Duplicate provenance JSON key")
            out[k]=v
        return out
    return json.loads(data,object_pairs_hook=pairs,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError("Nonfinite provenance JSON")))

def read_current_config(root,role):
    if role not in CONFIG_ROLES:raise ValueError("Unknown current configuration role")
    return _decode(_inside(root,"configs/tc2_gpu/"+role+".json").read_bytes())

current_config=read_current_config

def current_manifest(root):
    path=_inside(root,"configs/tc2_gpu/source_manifest.json")
    if not path.is_file():raise RuntimeError("Current source manifest has not been sealed")
    value=_decode(path.read_bytes())
    if value.get("schema_version")!="1.0" or value.get("workflow_id")!="tc2_gpu" or value.get("profile")!="current":
        raise ValueError("Invalid current source manifest")
    return value

def current_source_sha(root,name):
    name=_relative(name);actual=sha_file(_inside(root,name))
    manifest_path=_inside(root,"configs/tc2_gpu/source_manifest.json")
    if manifest_path.is_file():
        manifest=current_manifest(root)
        if manifest.get("status")=="sealed":
            expected=manifest["files"].get(name)
            if expected is None or expected!=actual:raise ValueError("Current source differs: "+name)
    return actual

def current_source_hashes(root,group="workflow"):
    manifest=current_manifest(root)
    group="full" if group=="all" else group
    names=manifest["groups"].get(group)
    if not isinstance(names,list) or not names or len(names)!=len(set(names)):
        raise ValueError("Invalid current source group: "+str(group))
    return {name:current_source_sha(root,name) for name in names}

source_group=current_source_hashes

def archive_index(root):
    root=_root(root);path=_inside(root,"archive/index.json");data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest().upper()
    manifest_path=_inside(root,"configs/tc2_gpu/source_manifest.json")
    if manifest_path.is_file():
        manifest=current_manifest(root)
        if manifest.get("status")=="sealed" and manifest.get("archive_index_sha256")!=digest:
            raise ValueError("Historical archive index changed")
    key=(str(root),digest)
    if key not in _INDEX_CACHE:
        index=_decode(data)
        if index.get("schema_version")!="1.0" or index.get("workflow_id")!="tc2_gpu":
            raise ValueError("Invalid historical archive index")
        _INDEX_CACHE[key]=index
    return _INDEX_CACHE[key]

def historical_entry(root,name):
    index=archive_index(root);name=_relative(name)
    if name not in index["entries"]:
        name=index.get("aliases",{}).get(name,name)
    entry=index["entries"].get(name)
    if entry is None:raise FileNotFoundError("Historical material is not indexed: "+name)
    _relative(entry["archive"]);_relative(entry["member"])
    if not entry["archive"].startswith("archive/"):raise ValueError("Historical ZIP must remain under archive")
    return entry

def historical_exists(root,name):
    try:historical_entry(root,name);return True
    except FileNotFoundError:return False

def _checked_archive(root,entry,force=False):
    index=archive_index(root);name=entry["archive"];path=_inside(root,name)
    expected=index["archives"].get(name)
    if expected is None:raise ValueError("Unregistered historical archive")
    stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns,expected["sha256"])
    if force or key not in _ARCHIVE_CACHE:
        if stat.st_size!=expected["size"] or sha_file(path)!=expected["sha256"]:
            raise ValueError("Historical ZIP fingerprint differs: "+name)
        _ARCHIVE_CACHE[key]=True
    return path

def historical_bytes(root,name):
    entry=historical_entry(root,name);path=_checked_archive(root,entry)
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)!=len({m.filename for m in members}):raise ValueError("Duplicate historical ZIP members")
        member=archive.getinfo(entry["member"])
        if member.is_dir() or member.file_size!=entry["size"]:raise ValueError("Historical member size differs")
        data=archive.read(member)
    if hashlib.sha256(data).hexdigest().upper()!=entry["sha256"]:
        raise ValueError("Historical member fingerprint differs: "+name)
    return data

def read_historical_json(root,name):
    return _decode(historical_bytes(root,name))

def historical_sha(root,name):
    # Reading also checks the bytes, not only the stored index.
    return hashlib.sha256(historical_bytes(root,name)).hexdigest().upper()

def historical_config(root,role):
    if role not in CONFIG_ROLES:raise ValueError("Unknown historical configuration role")
    return read_historical_json(root,archive_index(root)["roles"][role])

def historical_config_sha(root,role):
    return historical_sha(root,archive_index(root)["roles"][role])

def verify_archive(root):
    root=_root(root);index=archive_index(root);count=0;total=0
    by_archive={}
    for name,entry in index["entries"].items():by_archive.setdefault(entry["archive"],[]).append((name,entry))
    for filename,items in by_archive.items():
        path=_checked_archive(root,items[0][1],force=True)
        expected_members={entry["member"] for _,entry in items}
        with zipfile.ZipFile(path) as archive:
            members=archive.infolist()
            if len(members)!=len({m.filename for m in members}):raise ValueError("Duplicate historical ZIP member")
            actual={m.filename for m in members if not m.is_dir()}
            if actual!=expected_members:raise ValueError("Unindexed or missing historical ZIP member")
            for name,entry in items:
                info=archive.getinfo(entry["member"])
                if info.file_size!=entry["size"]:raise ValueError("Historical member size differs")
                h=hashlib.sha256()
                with archive.open(info) as stream:
                    for block in iter(lambda:stream.read(1024**2),b""):h.update(block)
                if h.hexdigest().upper()!=entry["sha256"]:raise ValueError("Historical member SHA differs: "+name)
                count+=1;total+=info.file_size
    return {"status":"passed","archive_count":len(by_archive),"members_verified":count,"bytes_verified":total,
            "physical_extraction_performed":False}

def require_current_acceptance(root,phase,design=None):
    root=_root(root);setup=read_current_config(root,"setup");deployment=setup.get("deployment",{})
    if deployment.get("status")!="configured":
        raise RuntimeError("Current TC2 GPU deployment is unavailable or not configured; historical jobs do not authorize this source.")
    manifest=current_manifest(root)
    if manifest.get("status")!="sealed":raise RuntimeError("Current source manifest must be sealed")
    relative=deployment.get("acceptance_records",{}).get(phase) or deployment.get("acceptance_record")
    if not relative:raise RuntimeError("Current source/environment acceptance is required for "+str(phase))
    receipt=_decode(_inside(root,relative).read_bytes())
    expected={
        "profile":"current","status":"passed","mode":"full","phase":phase,
        "source_manifest_sha256":sha_file(_inside(root,"configs/tc2_gpu/source_manifest.json")),
        "protocol_sha256":current_source_sha(root,"configs/tc2_gpu/protocol.json")}
    if any(receipt.get(k)!=v for k,v in expected.items()):
        raise RuntimeError("Current acceptance is missing or belongs to a different source/environment")
    current_source_hashes(root,"full")
    return receipt

