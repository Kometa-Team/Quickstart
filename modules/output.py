
def add_border_to_ascii_art(art):
    lines = art.split('\n')
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    return '\n'.join(bordered_art)
