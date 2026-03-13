# VHS tape file for recording the claude-sessions demo GIF
# Run: vhs assets/demo.tape

Output assets/demo.gif

Set Shell zsh
Set FontSize 14
Set Width 1400
Set Height 800
Set Padding 20
Set Theme "GitHub Dark"
Set TypingSpeed 60ms

# Launch
Type "claude-sessions --demo"
Enter
Sleep 3s

# Navigate down through sessions
Sleep 1s
Type "s"
Sleep 600ms
Type "s"
Sleep 600ms
Type "s"
Sleep 600ms
Type "s"
Sleep 600ms
Type "s"
Sleep 1s

# Collapse a group with A
Type "a"
Sleep 1s

# Navigate up
Type "w"
Sleep 500ms
Type "w"
Sleep 500ms

# Expand with D
Type "d"
Sleep 1s

# Switch to Topic dimension
Type "2"
Sleep 2s

# Navigate
Type "s"
Sleep 500ms
Type "s"
Sleep 500ms
Type "s"
Sleep 1s

# Switch to Domain dimension
Type "3"
Sleep 2s

# Navigate
Type "s"
Sleep 500ms
Type "s"
Sleep 1s

# Search
Type "/"
Sleep 500ms
Type "refactor"
Sleep 1.5s
Enter
Sleep 1s

# Navigate results
Type "s"
Sleep 800ms
Type "s"
Sleep 1s

# Clear search
Escape
Sleep 1.5s

# Switch to Date dimension
Type "4"
Sleep 2s

# Scroll detail pane
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Up
Sleep 300ms
Up
Sleep 1.5s

# Back to project view
Type "1"
Sleep 2s

# Quit
Type "q"
Sleep 1s
