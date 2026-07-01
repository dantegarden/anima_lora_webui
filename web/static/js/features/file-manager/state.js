export function createFileManagerState() {
    return {
        loading: false,
        uploading: false,
        roots: [],
        currentRoot: '',
        currentPath: '',
        entries: [],
        search: '',
        uploadTarget: '',
        uploadProgress: 0,
        extractJobId: '',
        lastPayload: null,
    };
}
