// Minimal JSX typings fallback when @types/react isn't installed yet.
declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
}
