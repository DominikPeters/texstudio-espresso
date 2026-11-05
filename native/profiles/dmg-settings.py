# dmgbuild settings; no Finder automation or visible windows are used.
app = defines['app']
files = [app]
symlinks = {'Applications': '/Applications'}
format = 'UDZO'
filesystem = 'HFS+'
volume_name = 'TeXstudio Espresso'
badge_icon = app + '/Contents/Resources/AppIconCoffee.icns'
background = 'builtin-arrow'
window_rect = ((200, 200), (640, 360))
default_view = 'icon-view'
show_toolbar = False
show_status_bar = False
show_pathbar = False
show_sidebar = False
icon_size = 96
text_size = 14
icon_locations = {'TeXstudio Espresso.app': (160, 170), 'Applications': (480, 170)}
