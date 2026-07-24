# FD-reader

**FD-reader** cross-checks the hotel's guest arrivals report against the
restaurant reservation lists so front desk doesn't have to manually eyeball both lists
against each other.

## What it's for

Front desk staff currently cross-reference two separate sources by hand:
the arrivals report (who's checking in, which room, any notes about a
dinner reservation) and the restaurant's own reservation system. Doing
that by eye is slow and easy to get wrong — a note can say a guest has a
7pm reservation at Artisans that was never actually booked, or Yelp can
show a reservation that doesn't match anyone arriving that week, or a
guest's room and the room mentioned in their reservation notes can simply
disagree.

FD-reader reads both PDFs and matches guests to their reservations
automatically, then produces one card per guest showing what it found —
so problems that would otherwise only surface as a guest complaint at
check-in, or a missed dinner reservation, get caught and fixed
beforehand instead. It's a second pair of eyes, not a replacement for
reading the reports — see `how_to_use.md`'s "Important" section.

Along the way it also flags data-quality issues in the arrivals report
itself (a room with no name assigned, a guest count that exceeds what the
room sleeps) that have nothing to do with
restaurant reservations but are just as easy to miss by eye.

