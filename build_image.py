"""Standalone inert fixture image builder. No home, environment, Docker auth or network reads.

Creates OCI layout plus Docker-load archive, statically; never executes a container.
This new test-only script may be uploaded separately, NOT the CredScope project.
"""
from pathlib import Path
from io import BytesIO
import argparse,gzip,hashlib,json,tarfile
IMAGE='ghcr.io/wanru463-pixel/credscope-oci-public-test:r20-controlled'
SOURCE='https://github.com/wanru463-pixel/credscope-oci-public-test'
SEED='CredScope-R20-never-issued-fixture-20261019-v1'
def json_bytes(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def digest(data):return 'sha256:'+hashlib.sha256(data).hexdigest()
def values():return {name:hashlib.shake_256((SEED+':'+name).encode()).hexdigest(24) for name in ['generic_api_token','oauth_client_secret','cloud_secret_key','password']}
def payloads(version):
    v=values();first=('api_token='+v['generic_api_token']+'\nclient_secret='+v['oauth_client_secret']+'\n').encode()
    second=('secret_access_key='+v['cloud_secret_key']+'\npassword='+v['password']+'\n').encode()
    normal=b'cache_digest=7f6c2e\nretry_count=3\nregion=local-fixture\napi_key=${API_KEY}\npassword=changeme\n'
    layers=[{'credscope-test/fixture-v1.env':first,'credscope-test/normal.conf':normal,
             'credscope-test/README.txt':b'INERT SYNTHETIC TEST ONLY. Never issued. No authentication rights. Do not run this container.\n'}]
    if version=='V2':layers.append({'credscope-test/fixture-v2.env':second,'credscope-test/normal-v2.json':b'{"enabled":true,"cache_digest":"ordinary-non-auth-text"}\n'})
    return layers
def tar_bytes(files):
    stream=BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tf:
        for name,data in sorted(files.items()):
            ti=tarfile.TarInfo(name);ti.size=len(data);ti.mtime=0;ti.mode=0o644;ti.uid=ti.gid=0;ti.uname=ti.gname='';tf.addfile(ti,BytesIO(data))
    return stream.getvalue()
def image(version):
    if version not in ['V1','V2']:raise ValueError('version_must_be_V1_or_V2')
    layers=[tar_bytes(files) for files in payloads(version)];zipped=[gzip.compress(x,mtime=0) for x in layers]
    config=json_bytes({'architecture':'amd64','os':'linux','config':{'Labels':{'org.opencontainers.image.source':SOURCE,'org.opencontainers.image.description':'CredScope inert static test only; no issued credentials; never run'}},
        'rootfs':{'type':'layers','diff_ids':[digest(x) for x in layers]},'history':[{'created_by':'CredScope inert fixture '+str(i+1)} for i in range(len(layers))]})
    blobs={digest(config):config,**{digest(z):z for z in zipped}}
    manifest={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
        'config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':digest(config),'size':len(config)},
        'layers':[{'mediaType':'application/vnd.oci.image.layer.v1.tar+gzip','digest':digest(z),'size':len(z)} for z in zipped]}
    raw=json_bytes(manifest);blobs[digest(raw)]=raw
    return {'version':version,'manifest':raw,'manifest_digest':digest(raw),'blobs':blobs,'uncompressed_layers':layers,'config':config,
        'files':{name:digest(data)[7:] for files in payloads(version) for name,data in files.items()}}
def build(version,out):
    if out.exists():raise FileExistsError('new_output_directory_required')
    out.mkdir(parents=True);im=image(version);layout=out/'oci-layout';(layout/'blobs/sha256').mkdir(parents=True)
    (layout/'oci-layout').write_bytes(json_bytes({'imageLayoutVersion':'1.0.0'}))
    index={'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json','manifests':[{'mediaType':'application/vnd.oci.image.manifest.v1+json','digest':im['manifest_digest'],'size':len(im['manifest']),
        'annotations':{'org.opencontainers.image.ref.name':'r20-controlled'}}]}
    (layout/'index.json').write_bytes(json_bytes(index))
    for dg,data in im['blobs'].items():(layout/'blobs/sha256'/dg[7:]).write_bytes(data)
    config_name=digest(im['config'])[7:]+'.json';archive_files={config_name:im['config']};layer_names=[]
    for raw in im['uncompressed_layers']:
        name=digest(raw)[7:]+'/layer.tar';layer_names.append(name);archive_files[name]=raw
    archive_files['manifest.json']=json_bytes([{'Config':config_name,'RepoTags':[IMAGE],'Layers':layer_names}])
    (out/'docker-image.tar').write_bytes(tar_bytes(archive_files))
    metadata={'fixture_version':version,'synthetic_only':True,'seed':SEED,'image_reference':IMAGE,'local_oci_manifest_digest':im['manifest_digest'],
        'config_digest':digest(im['config']),'layer_digests':[l['digest'] for l in json.loads(im['manifest'])['layers']],
        'rootfs_diff_ids':[digest(x) for x in im['uncompressed_layers']],'file_sha256':im['files'],
        'docker_archive_sha256':digest((out/'docker-image.tar').read_bytes())[7:],
        'docker_engine_import_executed':False,'remote_published':False,'note':'Docker engine push may serialize a Docker V2 manifest with a different digest. Public digest must be observed, not copied from this local OCI layout.'}
    (out/'fixture-lock.json').write_bytes(json_bytes(metadata))
    return metadata
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',choices=['V1','V2'],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    m=build(a.version,a.out);print(json.dumps({'version':a.version,'synthetic_only':True,'local_manifest_digest':m['local_oci_manifest_digest'],'files':len(m['file_sha256'])}))
