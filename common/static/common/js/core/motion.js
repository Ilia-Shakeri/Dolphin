// Scrolling that glides for most people and jumps for anyone who asked
// their system for reduced motion.
export function motionBehavior() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}
