def classFactory(iface):
    from .plugin import RoadImageLinkerPlugin
    return RoadImageLinkerPlugin(iface)