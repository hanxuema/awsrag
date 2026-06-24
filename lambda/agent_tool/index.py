import json

try:
    from shared.graph_repo import GraphRepository
except ModuleNotFoundError:
    import pathlib
    import sys

    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
    from shared.graph_repo import GraphRepository


class QueryService:
    def vector_search(self, query, top_k=3):
        import importlib.util
        import pathlib

        current_file = pathlib.Path(__file__).resolve()
        candidates = [
            current_file.parent / "query" / "index.py",
            current_file.parents[1] / "query" / "index.py",
        ]
        query_module_path = next(path for path in candidates if path.exists())
        spec = importlib.util.spec_from_file_location("query_index_for_agent_tool", query_module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.vector_search(query, top_k=top_k)

    def graph_search(self, query, limit=5):
        return GraphRepository().search_facts(query, limit=limit)


query_service = QueryService()


def get_parameter(event, name, default=None):
    for parameter in event.get("parameters", []):
        if parameter.get("name") == name:
            return parameter.get("value")
    return default


def agent_response(action_group, function_name, body):
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function_name,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(body)
                    }
                }
            },
        },
    }


def handler(event, context):
    print("Received agent tool event:", json.dumps(event))
    action_group = event.get("actionGroup", "KnowledgeTools")
    function_name = event.get("function")
    query = get_parameter(event, "query", "")

    if function_name == "vector_search":
        top_k = int(get_parameter(event, "top_k", 3))
        results = query_service.vector_search(query, top_k=top_k)
        return agent_response(action_group, function_name, {"results": results})

    if function_name == "graph_search":
        limit = int(get_parameter(event, "limit", 5))
        graph_result = query_service.graph_search(query, limit=limit)
        return agent_response(action_group, function_name, graph_result)

    return agent_response(
        action_group,
        function_name or "unknown",
        {"error": f"Unsupported function: {function_name}"},
    )
