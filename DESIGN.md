---
name: Lenny Growth Assistant
description: Quiet paper-and-green desktop workspace for grounded ideas.
colors:
  green: "#385b43"
  green-light: "#e5ebdf"
  paper: "#fcfcfa"
  sidebar: "#f2f3ee"
  line: "#e2e5dd"
  muted: "#626b5d"
  ink: "#292d29"
  white: "#ffffff"
typography:
  display:
    fontFamily: "Lora, Georgia, serif"
    fontSize: "clamp(34px, 3.5vw, 48px)"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-1.4px"
  headline:
    fontFamily: "Lora, Georgia, serif"
    fontSize: "30px"
    fontWeight: 500
    lineHeight: 1.35
  body:
    fontFamily: "DM Sans, system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: 1.85
  code:
    fontFamily: "Consolas, monospace"
    fontSize: "12px"
    lineHeight: 1.8
rounded:
  control: "6px"
  button: "8px"
  card: "10px"
  composer: "12px"
spacing:
  small: "8px"
  medium: "12px"
  large: "16px"
  section: "32px"
components:
  send:
    backgroundColor: "{colors.green}"
    textColor: "{colors.white}"
    rounded: "{rounded.button}"
    width: "33px"
    height: "33px"
  new-conversation:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.button}"
    padding: "12px 10px"
  composer:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.composer}"
    padding: "17px 16px 12px"
  navigation-active:
    backgroundColor: "{colors.green-light}"
    padding: "11px 12px"
  artifact-card:
    rounded: "{rounded.card}"
    padding: "17px"
---

# Design System: Lenny Growth Assistant

## Overview

**Creative North Star: "Quiet paper-and-green workspace"**

A restrained, familiar desktop chat workspace with an editorial reading surface. Warm paper, muted greens, and generous reading space support sustained thought; compact navigation and controls keep the surrounding interface quiet.

**Key Characteristics:**
- Paper surfaces with tonal separation.
- Serif headlines paired with compact sans-serif controls.
- Conversation first, with an optional adjacent artifact viewer.

This document records the implemented desktop design in `frontend/src/style.css` and `frontend/src/main.js`. It does not claim a separate visual audit or mobile design pass.

## Colors

### Primary
- **Forest green** (`green`) marks sending, primary actions, links, and keyboard focus.
- **Pale sage** (`green-light`) identifies active navigation.

### Neutral
- **Warm paper** (`paper`) is the main canvas; **mist sage** (`sidebar`) separates navigation.
- **Soft olive line** (`line`) divides lists and panels without heavy framing.
- **Muted moss** (`muted`) supports secondary labels; **charcoal ink** (`ink`) supplies base text.
- **White** (`white`) lifts the composer and artifact viewer through tone.

## Typography

Lora with Georgia fallback supplies the welcome heading and essay title; DM Sans with system-ui fallback supplies reading text and controls. Consolas supplies source code. Display and essay hierarchy use the frontmatter roles; prose subheads use sans-serif (20px and 16px), while most controls stay compact (11–13px). Body copy uses open line spacing for long answers.

## Layout

A full-height flex workspace holds a fixed sidebar (254px), flexible conversation, and optional artifact viewer (46% width, 360–760px). The header is 73px high. Centered welcome, message, and composer containers cap at 710px, 800px, and 830px respectively. Conversation and artifact content scroll independently; the composer remains at the bottom.

At desktop widths up to 1150px, opening an artifact hides the sidebar and sets the viewer to 48%. Above 1600px, welcome top spacing increases. Short desktop windows reduce welcome spacing. Existing smaller-screen fallback rules are outside this desktop documentation scope.

## Elevation & Depth

Large surfaces are flat, separated by pale borders and background tone. Only selected viewer tabs and transient toast feedback carry small shadows; their exact values live in the sidecar.

**The Quiet Surface Rule.** Keep primary reading surfaces flat; reserve shadows for selected tabs and transient feedback.

## Shapes

Controls, buttons, cards, and the composer use the gently curved radii in frontmatter. User messages have a distinctive asymmetric corner treatment (14px 14px 3px 14px). Most separators and container outlines are one pixel. Small line icons use a consistent stroke weight (1.7).

## Components

- **Buttons:** compact and restrained. Sending uses forest green, darkens on hover, and becomes pale when disabled. New conversation uses a white bordered treatment. Ghost icon buttons use a pale hover surface. Keyboard focus uses a green outline (2px, 4px offset).
- **Inputs / Fields:** the white composer contains a growing textarea, model selector, and send control. Skill selection follows the user's request automatically. Its border changes on focus; the textarea relies on that container treatment. History search is visually borderless. Welcome suggestions demonstrate questions, essays, and tools in one conversation.
- **Navigation:** compact rows use pale sage for the active section and a tonal hover state. Recent conversation titles truncate. Delete controls appear on hover or keyboard focus.
- **Cards / Containers:** artifact cards use a pale green surface, thin border, file icon, title, and secondary label; hover strengthens their outline. They open the adjacent viewer.
- **Citation chips:** small inline green-tinted references sit within the answer, complemented by expandable source details.
- **Artifact viewer:** a title header and compact view switch sit above readable Markdown, formatted code, or an isolated HTML preview. Copy, download, and close stay in the header area.
- **Feedback:** waiting combines text with a softly pulsing dot (1.2s); errors use a warm tinted strip and Retry. Reduced-motion preferences disable animation and smooth scrolling.

## Do's and Don'ts

### Do:
- **Do** preserve readable prose, compact controls, and visible source references.
- **Do** use green for actions and selection, with paper tones separating surfaces.
- **Do** retain visible keyboard focus and reduced-motion behavior.

### Don't:
- **Don't** add heavy shadows to the main reading surfaces.
- **Don't** turn the optional artifact viewer into a complex coding environment.
