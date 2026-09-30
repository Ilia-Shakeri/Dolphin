export function setupDocumentPrint() {
    document.getElementById("print-document")?.addEventListener("click", () => window.print());
}
