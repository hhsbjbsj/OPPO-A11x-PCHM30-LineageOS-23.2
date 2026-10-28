from pathlib import Path
import json,re,sys
BASE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BASE/'tools/python-deps'))
from tree_sitter import Language,Parser
import tree_sitter_java
PARSER=Parser(Language(tree_sitter_java.language()))
def walk(n):
    yield n
    for c in n.named_children:yield from walk(c)
def methods(b):
    tree=PARSER.parse(b);assert not tree.root_node.has_error
    result=[]
    for n in walk(tree.root_node):
        if n.type not in ('method_declaration','constructor_declaration'):continue
        name=n.child_by_field_name('name').text.decode();typ=n.child_by_field_name('type')
        ps=n.child_by_field_name('parameters');body=n.child_by_field_name('body')
        owner=n.parent
        while owner and owner.type not in ('class_declaration','interface_declaration'):owner=owner.parent
        def parameter_name(p):
            name=p.child_by_field_name('name')
            if name:return name.text.decode()
            return [c.text.decode() for c in walk(p) if c.type=='identifier'][-1]
        result.append({'name':name,'type':typ.text.decode() if typ else 'constructor',
            'parameters':[parameter_name(p) for p in ps.named_children if p.type in ('formal_parameter','spread_parameter')],
            'owner':owner.child_by_field_name('name').text.decode() if owner else None,
            'start':n.start_byte,'end':n.end_byte,'body_start':body.start_byte if body else None,
            'body_end':body.end_byte if body else None})
    return result
if __name__=='__main__':
    for filename in sys.argv[1:]:
        print(filename,json.dumps(methods(Path(filename).read_bytes()),indent=2))
