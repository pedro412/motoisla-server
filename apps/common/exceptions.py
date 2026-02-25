from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    if isinstance(response.data, dict):
        detail = response.data.get("detail", "Request failed")
        fields = {k: v for k, v in response.data.items() if k != "detail"}
    else:
        detail = "Request failed"
        fields = {}

    response.data = {
        "code": getattr(exc, "default_code", "error"),
        "detail": detail,
        "fields": fields,
    }
    return response
