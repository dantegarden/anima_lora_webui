export async function fetchFileManagerRoots(ctx) {
    return ctx.api('/api/file-manager/roots');
}

export async function fetchFileManagerList(ctx, root, path = '') {
    const params = new URLSearchParams({ root });
    if (path) params.set('path', path);
    return ctx.api(`/api/file-manager/list?${params.toString()}`); // '/api/file-manager/list'
}

export function uploadFileManagerFile(_ctx, { root, targetPath, file, onProgress } = {}) {
    return new Promise((resolve, reject) => {
        const form = new FormData();
        form.append('root', root || '');
        form.append('target_path', targetPath || '');
        form.append('file', file, file?.name || 'uploaded.bin');
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/file-manager/upload'); // '/api/file-manager/upload'
        xhr.responseType = 'text';
        xhr.upload?.addEventListener('progress', (event) => {
            if (!event.lengthComputable || typeof onProgress !== 'function') return;
            onProgress({
                loaded: event.loaded || 0,
                total: event.total || 0,
                percent: event.total ? Math.round((event.loaded / event.total) * 100) : 0,
            });
        });
        xhr.onload = () => {
            let payload = {};
            try {
                payload = xhr.responseText ? JSON.parse(xhr.responseText) : {};
            } catch {
                payload = { ok: false, error: xhr.responseText || `HTTP ${xhr.status}` };
            }
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(payload);
                return;
            }
            reject(new Error(payload.error || xhr.responseText || `HTTP ${xhr.status}`));
        };
        xhr.onerror = () => reject(new Error('上传请求失败'));
        xhr.send(form);
    });
}

export async function planFileManagerExtract(ctx, { root, archivePath, targetDir, overwrite = false } = {}) {
    return ctx.api('/api/file-manager/extract/plan', {
        method: 'POST',
        body: JSON.stringify({
            root,
            archive_path: archivePath,
            target_dir: targetDir,
            overwrite,
        }),
    });
}

export async function runFileManagerExtract(ctx, { root, archivePath, targetDir, overwrite = false } = {}) {
    return ctx.api('/api/file-manager/extract/run', {
        method: 'POST',
        body: JSON.stringify({
            root,
            archive_path: archivePath,
            target_dir: targetDir,
            overwrite,
        }),
    });
}

export async function fetchFileManagerJobStatus(ctx, jobId) {
    return ctx.api(`/api/file-manager/jobs/${encodeURIComponent(jobId)}`); // '/api/file-manager/jobs/'
}

export async function renameFileManagerEntry(ctx, { root, path, newName } = {}) {
    return ctx.api('/api/file-manager/rename', {
        method: 'POST',
        body: JSON.stringify({
            root,
            path,
            new_name: newName,
        }),
    });
}

export async function deleteFileManagerEntry(ctx, { root, path } = {}) {
    return ctx.api('/api/file-manager/delete', {
        method: 'POST',
        body: JSON.stringify({
            root,
            path,
        }),
    });
}

export function buildFileManagerDownloadUrl(root, path) {
    const params = new URLSearchParams({ root, path });
    return `/api/file-manager/download?${params.toString()}`;
}
