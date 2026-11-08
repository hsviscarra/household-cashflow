# ADR-049: Choose light or dark

Status: accepted (0.63.1, Nov 2026)

## Context

The app followed the device: Hernan's Mac is in dark mode, so he saw the dark palette while
previews (rendered light) showed the Clear light look, and it seemed the redesign never shipped.

## Decision

- A Theme switch at the bottom of the sidebar: Auto (as the device), Light or Dark, saved with
  each person's settings (`theme`) and applied as `data-theme` on `<html>`.
- CSS: the dark tokens apply under `prefers-color-scheme: dark` unless Light is chosen, and always
  with `data-theme="dark"`. No other style changes.
