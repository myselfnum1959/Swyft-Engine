# Script language reference

Scripts are `.swy` text files. Indentation is 4 spaces (tabs are rejected). `#` starts a comment.

## Top level

```text
character mira "Mira" color "#7fd1ff"    # id, display name, optional name-tag colour
default courage = 0                       # variable with its starting value (a literal, no variables)
label start:                              # all story lines live inside labels
    ...
```

Labels flow into the next label if they don't `jump` or `end` (like chapters).
`start` is the default entry label.

## Statements

| Statement | Meaning |
|---|---|
| `"Text"` | Narration |
| `mira "Text"` | Dialogue (speaker must be declared with `character`) |
| `set x = expr` / `+=` `-=` `*=` `/=` | Change a variable |
| `jump label` | Go to a label |
| `end` | End the story |
| `if cond:` / `elif cond:` / `else:` | Conditional blocks |
| `menu:` | Choices (below) |
| `scene name [instant]` | Change background (clears the stage; fades in unless `instant`) |
| `show who [expr] [at left\|center\|right\|farleft\|farright\|0.3]` | Show a character |
| `hide who` | Remove a character |
| `music "file"` / `music stop` | Background music (`assets/music/file`) |
| `sound "file"` | Sound effect (`assets/sounds/file`) |
| `wait seconds` | Pause |
| `shake [intensity] [seconds]` | Screen shake |

### Menus

```text
menu:
    "Always shown":
        set courage += 1
    "Only if brave" if courage >= 2:
        jump brave_path
```

Options whose condition is false are hidden. Every option falls through to the line after the menu unless it jumps.

### Text interpolation

`"You have {gold} coins. Literal braces: {{ }}"`

## Expressions

Numbers, strings, `true` / `false` / `none`, variables, `+ - * / // %`, comparisons (`== != < <= > >= in not in`, chainable),
`and or not`, list literals. The special name `visited` is the set of labels reached so far:
`if "cave" in visited:`.

Not allowed (by design): function calls, attribute access, `**`, comprehensions, lambdas.

## Errors

```text
$ python -m swyft check story.swy
error: story.swy:14: jump to unknown label 'finalee' - did you mean 'finale'?
```

Checked at load time: unknown labels / variables / speakers, duplicate labels, bad indentation,
unterminated strings, unsafe expressions, reserved words.

## Custom commands

```python
story = load_story("story.swy", extra_commands=["flash"])
scene = StoryScene(story)
scene.register_command("flash", lambda args: print("flash", args))
```
