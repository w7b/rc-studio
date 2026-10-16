// Native modal dialogs make every element outside their top layer inert.
// Keep child overlays in that layer while escaping scrollable content containers.
export function overlayRoot(anchor) {
  return anchor?.closest('dialog[open]') || document.body;
}
