"""Keyboard selection in a scrolled list of cards (the overview, the minimized
picker): scroll just enough that the selected card is in view (specs NAV,
PICKNAV)."""


def scroll_to_show(top, bottom, value, page, margin=16):
    """NAV-1: the scroll position that shows a card spanning top..bottom (list
    coordinates) with `margin` around it, moving as little as possible; None when
    the card is already in view (value..value+page)."""
    if top < value:
        return max(0, top - margin)
    if bottom > value + page:
        return bottom - page + margin
    return None


def reveal(scroll, content, widget):
    """Scroll `scroll` (a Gtk.ScrolledWindow around `content`) so `widget`, a
    card inside `content`, is in view. Nothing before GTK has laid it out."""
    ok, rect = widget.compute_bounds(content)
    if not ok:
        return
    adj = scroll.get_vadjustment()
    to = scroll_to_show(rect.get_y(), rect.get_y() + rect.get_height(), adj.get_value(), adj.get_page_size())
    if to is not None:
        adj.set_value(to)
