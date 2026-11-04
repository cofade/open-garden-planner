## Case study: global 3D actions changed a hidden workspace (#539, PR #565)

**Symptom.** View -> 3D View changed nothing visible from Calendar.
**Wrong theory.** Setting Split alone was treated as making its pane visible.
**Evidence.** The integration workflow triggers the global action from Calendar,
then a real Alt+3 from Seed Inventory, and asserts the current tab and pane.
The workspace is a child of Garden Plan; changing its mode cannot select that tab.
**Root cause.** Global navigation only changed local workspace state.
**Fix.** The main window selects Garden Plan for the show action and global mode
actions. Alt+1 still requests Plan; Alt+2/3 request 3D/Split.
**Lesson.** Assert the containing tab as well as the child mode for global navigation.

