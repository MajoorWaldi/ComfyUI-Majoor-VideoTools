---
name: Unoccupied location check
kind: analyzer
description: Check an unoccupied location for actual people before it becomes a background reference.
---
Inspect only the attached image. Is this an unoccupied location, with no actual people? Furniture, objects and lamps are allowed: unoccupied does not mean unfurnished.
Actual people include partial bodies, silhouettes, reflections of real people and background crowds. A clearly flat printed figure on a surface is not an actual person; mention that distinction in the reason. If you cannot distinguish a depiction from an actual person, use uncertain. A dark or unreadable image is uncertain. Do not infer the absence of people from the request or the filename.
Return ONLY one JSON object: {"status":"clear|person|uncertain","reason":"brief visual evidence"}.
Use clear only when the visible scene contains no actual people and any printed figure is unambiguously flat print. Use person if an actual person is visible, including a reflection or partial body. Otherwise use uncertain. Do not include markdown, a score or a promise of certainty.
