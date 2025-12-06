import threading

_thread_local = threading.local()


def get_current_tenant():
    return getattr(_thread_local, "tenant", None)


def set_current_tenant(tenant):
    _thread_local.tenant = tenant


def reset_current_tenant():
    if hasattr(_thread_local, "tenant"):
        del _thread_local.tenant
