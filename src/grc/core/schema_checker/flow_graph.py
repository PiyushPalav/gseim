from .utils import Spec, expand, str_

OPTIONS_SCHEME = expand(
    parameters=Spec(types=dict, required=False, item_scheme=(str_, str_)),
    states=Spec(types=dict, required=False, item_scheme=(str_, str_)),
)

BLOCK_SCHEME = expand(
    name=str_,
    id=str_,
    outvars=str_,
    **OPTIONS_SCHEME
)

FLOW_GRAPH_SCHEME = expand(
    options=Spec(types=dict, required=False, item_scheme=OPTIONS_SCHEME),
    blocks=Spec(types=dict, required=False, item_scheme=BLOCK_SCHEME),
    connections=list,

)
