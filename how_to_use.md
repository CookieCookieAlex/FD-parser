# How to Use — Guest × Yelp Reservation Cross-Check

*(This is a draft for the in-app "ℹ️ How to use" popup. Three tabs: **Important**, **About**, **How to start**.)*

---

## Tab 1: Important

⚠️ **This is a helper tool, not a replacement for reading the reports yourself.**

- It's built to catch things faster — it can still get things wrong or break.
- Always double-check anything flagged 🔴 or 🟡 against the real PDFs before acting on it.
- Don't rely on it as the single source of truth. Manual read-through is still essential.

---

## Tab 2: About

**What this does:** compares the hotel's arrival list against the Yelp for
dinner reservations, so you don't have to manually check both lists against
each other.

It also shows you the Virtuoso and Breakfast Included notes, pulled from the guest notes.

It gives you quick info about the guest: arrival, departure, rate, room
type, room name, confirmation ID, and guest count per room.

It shows you if the guest is moving rooms — by checking if the room type
or name changes during their stay, or if the departure and arrival dates
match up under the same guest name.

It also shows you if a guest is part of a group booking.

**What to expect:** one card per guest, color-coded 🟢 matched · 🟡 needs a
look · 🔴 mismatch · 🔵 no reservation, each with a short note underneath
explaining what was found.
A faster way to spot what the notes might have
missed, not a final verdict.

---

## Tab 3: How to start

### A. Make a folder where you will save PDF's

1. Go to Dekstop and press right click and make a folder.
   Name it as you like.
2. Do not change the name of the files — it will not work if you rename them.

### B. Get the arrival notes (HMS)

1. In HMS, open the ☰ burger menu → search **"Advance Arrival with Details"**.
2. Scroll down and set:
   - **Sort by:** Arrival Date
   - **End date:** 7 days out from today
   - ⚠️ Don't set it further than 7 days — the report comes back as a blank PDF.
      If that happens, pull the end date back one day at a time until it shows data.
3. Click **Print** / **Show** at the top of HMS — it opens as a PDF.
4. `Ctrl + S` to save it into a folder you've made for this.

### C. Get the Yelp reservations (one day at a time)

1. Go to Yelp for Business reservations.
2. Yelp only exports **one day per PDF** — open each day in the *same* 7-day range as the arrival notes, one at a time.
3. `Ctrl + S` each day's PDF into the **same folder** as the arrival notes.
4. Repeat for all 7 days. You should end up with **8 PDFs total**. 1 arrival notes + 7 Yelp days.

**The date ranges must match.** Yelp days and the arrival notes need to
start and end on the same dates — otherwise the tool is comparing different
weeks.

### D. Load it into the tool

- **Folder path:** paste the folder's path into the "Folder path" box, or
- **Upload files:** click "Upload files" and select all 8 PDFs at once.

Then click **Load** and wait for the cards to appear.
