def classFactory(iface):
    from .plugin import KakaoQgisBridgePlugin

    return KakaoQgisBridgePlugin(iface)
