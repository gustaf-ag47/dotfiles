# Dunst Notification Position Examples

## Current Setting (Centered Top)
```ini
origin = top-center
offset = (0, 50)
```

## Alternative Positions

### Center of Screen
```ini
origin = center
offset = (0, 0)
```

### Bottom Center
```ini
origin = bottom-center
offset = (0, -50)
```

### Top Right (original)
```ini
origin = top-right
offset = (30, 50)
```

### Top Left
```ini
origin = top-left
offset = (30, 50)
```

### Bottom Right
```ini
origin = bottom-right
offset = (30, -50)
```

### Bottom Left
```ini
origin = bottom-left
offset = (30, -50)
```

## Multi-Monitor Setup

For multi-monitor setups, you can specify which monitor:
```ini
monitor = 0    # Primary monitor
monitor = 1    # Secondary monitor
```

Or follow the mouse cursor:
```ini
follow = mouse
```

## Custom Offset Examples

### Slightly off-center to the right
```ini
origin = top-center
offset = (100, 50)
```

### Higher up on screen
```ini
origin = top-center
offset = (0, 20)
```

### Lower on screen
```ini
origin = top-center
offset = (0, 100)
```

To change position, edit the dunst config and restart dunst:
```bash
vim ~/.config/dunst/dunstrc
killall dunst && dunst &
```