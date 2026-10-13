from pathlib import Path
import hashlib, json, subprocess, sys, yaml

ROOT=Path(__file__).resolve().parents[2]
M=ROOT/'matrix.yaml'; S=ROOT/'matrix_schema.json'; V=ROOT/'tools/validate_matrix.py'; C=ROOT/'tools/compare_source_markdown.py'; E=ROOT/'tools/check_evidence.py'

def run(*args, cwd=ROOT): return subprocess.run([sys.executable,*map(str,args)],cwd=cwd,text=True,capture_output=True)

def mutate_matrix(tmp_path, fn):
    d=yaml.safe_load(M.read_text()); fn(d); p=tmp_path/'matrix.yaml'; p.write_text(yaml.safe_dump(d,sort_keys=False)); return p

def test_validator_rejects_bad_citation(tmp_path):
    p=mutate_matrix(tmp_path, lambda d:d['acceptance_rows'][0]['source_citations'].__setitem__(0,'[M1 §999]'))
    r=run(V,p,'--schema',S,'--m1',ROOT/'docs/source/milestone_1.md','--m12',ROOT/'docs/source/milestone_1_2.md'); assert r.returncode != 0

def test_validator_rejects_changed_row_count(tmp_path):
    p=mutate_matrix(tmp_path, lambda d:d['acceptance_rows'].pop())
    r=run(V,p,'--schema',S,'--m1',ROOT/'docs/source/milestone_1.md','--m12',ROOT/'docs/source/milestone_1_2.md'); assert r.returncode != 0

def test_validator_rejects_item_binding_not_in_row_tests(tmp_path):
    def f(d): d['acceptance_rows'][0]['source_item_bindings']['[M1 §28 #1]']=['tests/unit/test_config.py::not_in_tests']
    p=mutate_matrix(tmp_path,f); r=run(V,p,'--schema',S,'--m1',ROOT/'docs/source/milestone_1.md','--m12',ROOT/'docs/source/milestone_1_2.md'); assert r.returncode != 0

def test_schema_rejects_duplicate_tests(tmp_path):
    d=yaml.safe_load(M.read_text()); d['acceptance_rows'][0]['tests']=[d['acceptance_rows'][0]['tests'][0]]*2
    p=tmp_path/'matrix.yaml'; p.write_text(yaml.safe_dump(d,sort_keys=False)); r=run(V,p,'--schema',S,'--m1',ROOT/'docs/source/milestone_1.md','--m12',ROOT/'docs/source/milestone_1_2.md'); assert r.returncode != 0

def test_source_comparison_against_reviewer_copy_passes():
    r=run(C,ROOT/'docs/source/milestone_1.md',ROOT/'reviewer/project_source_m1.md'); assert r.returncode==0
    r=run(C,ROOT/'docs/source/milestone_1_2.md',ROOT/'reviewer/project_source_m1_2.md'); assert r.returncode==0

def test_source_comparison_intentional_difference_fails(tmp_path):
    bad=tmp_path/'bad.md'; bad.write_text((ROOT/'reviewer/project_source_m1.md').read_text()+'\nINTENTIONAL DIFFERENCE\n'); r=run(C,ROOT/'docs/source/milestone_1.md',bad); assert r.returncode!=0

def test_evidence_hash_mismatch_fails(tmp_path):
    root=tmp_path/'root'; root.mkdir(); f=root/'artifact.txt'; f.write_text('artifact'); (root/'commit.txt').write_text('a'*40); (root/'manifest.txt').write_text('0'*64+' artifact.txt\n')
    r=run(E,M,'--root',root,'--commit-file',root/'commit.txt','--manifest',root/'manifest.txt'); assert r.returncode!=0

def test_evidence_path_escape_fails(tmp_path):
    root=tmp_path/'root'; root.mkdir(); (root/'commit.txt').write_text('a'*40); outside=tmp_path/'outside.txt'; outside.write_text('x'); (root/'manifest.txt').write_text('00'*32+' ../outside.txt\n')
    r=run(E,M,'--root',root,'--commit-file',root/'commit.txt','--manifest',root/'manifest.txt'); assert r.returncode!=0

def test_evidence_missing_commit_fails(tmp_path):
    root=tmp_path/'root'; root.mkdir(); (root/'commit.txt').write_text('abc'); (root/'manifest.txt').write_text('')
    r=run(E,M,'--root',root,'--commit-file',root/'commit.txt','--manifest',root/'manifest.txt'); assert r.returncode!=0

def test_evidence_positive_with_commit_record_and_manifest(tmp_path):
    root=tmp_path/'root'; root.mkdir(); artifact=root/'evidence'/'x.txt'; artifact.parent.mkdir(); artifact.write_text('x')
    commit='a'*40; (root/'commit.txt').write_text(commit); h=hashlib.sha256(artifact.read_bytes()).hexdigest(); (root/'manifest.txt').write_text(f'{h} evidence/x.txt\n')
    matrix=tmp_path/'m.yaml'; matrix.write_text(yaml.safe_dump({'acceptance_rows':[{'artifact_path':'evidence/x.txt'}]}))
    r=run(E,matrix,'--root',root,'--commit-file',root/'commit.txt','--manifest',root/'manifest.txt'); assert r.returncode==0


def test_schema_rejects_empty_tests(tmp_path):
    p=mutate_matrix(tmp_path, lambda d:d['acceptance_rows'][0].__setitem__('tests',[]))
    r=run(V,p,'--schema',S,'--m1',ROOT/'docs/source/milestone_1.md','--m12',ROOT/'docs/source/milestone_1_2.md'); assert r.returncode != 0

def test_traceability_rejects_mandatory_row_without_tests(tmp_path):
    root=tmp_path/'root'; (root/'tests'/'unit').mkdir(parents=True)
    testfile=root/'tests'/'unit'/'test_empty_binding.py'
    testfile.write_text('import pytest\n@pytest.mark.requirement("HOST-01")\ndef test_host():\n    assert 1 == 1\n')
    junit=root/'offline.xml'; junit.write_text('<testsuite><testcase classname="tests.unit.test_empty_binding" name="test_host"><properties><property name="requirement" value="HOST-01"/></properties></testcase></testsuite>')
    matrix=tmp_path/'matrix.yaml'; matrix.write_text(yaml.safe_dump({'acceptance_rows':[{'id':'HOST-01','mandatory':True,'tests':[],'evidence_class':'offline','stage':1,'source_item_bindings':{}}]}))
    r=run(ROOT/'tools/check_traceability.py',matrix,'--root',root,'--junit','offline='+str(junit),'--stage','1'); assert r.returncode != 0


def test_source_comparison_detects_item_number_change(tmp_path):
    original=(ROOT/'reviewer/project_source_m1_2.md').read_text()
    bad=tmp_path/'bad-number.md'
    bad.write_text(original.replace('1. [ ] Server-time endpoint failure causes the fetch to abort.', '99. [ ] Server-time endpoint failure causes the fetch to abort.', 1))
    r=run(C,ROOT/'docs/source/milestone_1_2.md',bad); assert r.returncode!=0
    assert '99. [ ] Server-time endpoint failure causes the fetch to abort.' in r.stdout
