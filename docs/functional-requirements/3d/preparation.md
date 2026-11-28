---
title: "3D scene preparation"
prefixes: ["FR-3D-PREP"]
---

# 3D scene preparation

- **FR-3D-PREP-01** (#452, ADR-069): Opening or editing a large plan keeps the window
  responsive while the 3D view prepares it. A whole-plan read runs in 4 ms slices
  between turns of the event loop, one item per step, and a plan's geometry whose
  changed outlines hold 20,000 vertices or more is built on one worker lane and
  applied when it answers. Measured on the issue's three plans (160 polygons of 1,000
  vertices; 1,600 of 100; 110 closed fences of 801): the GUI heartbeat's p95 is
  1.7-3.6 ms and its maximum 8-20 ms, against 4.0/5.4/12.6 s held in one block before.
  The records are the same records: no budget across the plan, so one item's record
  never depends on what else is on the plan. A change during the read applies the
  coherent earlier snapshot (an item deleted since is dropped) and is read again at
  once; a document change, a reset, hiding 3D or shutdown drop the read, so a new plan
  is never assembled from the old one's items. A read that outlasts a quarter second
  says "Updating the 3D view…" on the status line.
- **FR-3D-PREP-02** (#452, ADR-069): A long but honest outline gets a solid. A drawn
  region up to 16,384 vertices and a stroke whose region is within the work bound are
  cut by the native triangulation; a 4,096-vertex ring and a slab with 200 touching
  holes are buildable, where the shared ear clipper left a real traced path of about
  900 points out of 3D. What is still refused (a 16,384-vertex circle, a dense
  scribble beyond 150 M work units) is named in the problems list, as before.
