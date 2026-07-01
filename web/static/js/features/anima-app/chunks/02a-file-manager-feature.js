const ctx = globalThis.ctx;

globalThis.fileManagerFeature = null;
globalThis.ensureFileManagerFeature = function ensureFileManagerFeature() {
    if (fileManagerFeature) return fileManagerFeature;
    fileManagerFeature = createFileManagerFeature(ctx);
    return fileManagerFeature;
}
