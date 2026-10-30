"""统一错误结构 ``{"error": {"code", "message", "request_id"}}`` 与错误码中文文案。

路由以 ``HTTPException(status_code, detail="UPPER_SNAKE_CODE")`` 抛出业务错误，
由 ``main.py`` 的全局处理器经此模块转换；前端直接展示 ``message``。
"""

from fastapi import Request
from fastapi.responses import JSONResponse

MESSAGES: dict[str, str] = {
    # 通用
    "INVALID_PARAMETER": "请求参数不合法",
    "VALIDATION_ERROR": "请求参数不合法（请检查输入）",
    "UNAUTHENTICATED": "未登录或会话已过期",
    "FORBIDDEN": "当前角色无权执行该操作",
    "NOT_FOUND": "请求的资源不存在",
    "METHOD_NOT_ALLOWED": "请求方法不被允许",
    "INVALID_STATE": "当前状态不允许此操作",
    "CSRF": "缺少或错误的 CSRF Token",
    "DEPENDENCY_UNAVAILABLE": "依赖服务不可用，请稍后重试",
    "HTTP_ERROR": "请求失败",
    # 认证
    "INVALID_CREDENTIALS": "用户名或密码错误",
    "ACCOUNT_DISABLED": "账号已停用",
    "LOGIN_RATE_LIMITED": "尝试过于频繁，请稍后再试",
    # 预警
    "PARTIAL_DATA": "数据不完整，无法创建正式预警",
    "THRESHOLD_NOT_REACHED": "融合值未达到所选阈值，无法创建预警",
    "SELF_REVIEW_FORBIDDEN": "不能审核自己创建的预警",
    "REJECT_REQUIRES_COMMENT": "驳回时必须填写审核意见",
    # 用户管理
    "USERNAME_EXISTS": "用户名已存在",
    "LAST_ADMIN_REQUIRED": "系统至少需要一名管理员",
    "SELF_DISABLE_FORBIDDEN": "不能停用当前登录账号",
    "SELF_ADMIN_REMOVAL_FORBIDDEN": "不能撤销当前登录账号的管理员角色",
}

# 框架自身抛出的 HTTP 错误（如未匹配路由）没有业务码，按状态码兜底
_STATUS_CODES: dict[int, str] = {
    400: "INVALID_PARAMETER",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "INVALID_STATE",
    422: "VALIDATION_ERROR",
    503: "DEPENDENCY_UNAVAILABLE",
}


def code_for(status_code: int, detail: object) -> str:
    if isinstance(detail, str) and detail in MESSAGES:
        return detail
    return _STATUS_CODES.get(status_code, "HTTP_ERROR")


def error_response(request: Request, status_code: int, code: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": MESSAGES.get(code, MESSAGES["HTTP_ERROR"]),
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        headers=headers,
    )
