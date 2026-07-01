import {
    buildFileManagerDownloadUrl,
    fetchFileManagerJobStatus,
    fetchFileManagerList,
    fetchFileManagerRoots,
    planFileManagerExtract,
    renameFileManagerEntry,
    runFileManagerExtract,
    uploadFileManagerFile,
} from './api.js?v=module-bootstrap-20260627-3';
import { createFileManagerRenderer } from './render.js?v=module-bootstrap-20260627-3';
import { createFileManagerState } from './state.js?v=module-bootstrap-20260627-3';

export function createFileManagerFeature(ctx) {
    const state = createFileManagerState();
    const renderer = createFileManagerRenderer({ state });

    async function loadFileManagerRoots(options = {}) {
        if (state.loading && !options.force) return;
        if (location.protocol === 'file:') {
            renderer.setStatus('静态打开没有后端 API，无法浏览容器目录。', 'error');
            return;
        }
        state.loading = true;
        renderer.setStatus('正在读取文件管理根目录...', '');
        try {
            const payload = await fetchFileManagerRoots(ctx);
            state.roots = payload.roots || [];
            if (!state.currentRoot && state.roots.length) {
                state.currentRoot = state.roots[0].id || '';
                state.currentPath = state.roots[0].path || '';
            }
            if (!state.uploadTarget) {
                state.uploadTarget = state.currentPath;
            }
            renderer.renderRoots();
            if (state.currentRoot) {
                await loadCurrentDirectory({ force: true });
            } else {
                renderer.setStatus('没有可用的文件管理根目录。', 'error');
            }
        } catch (error) {
            renderer.setStatus(`读取文件管理根目录失败: ${error.message}`, 'error');
        } finally {
            state.loading = false;
        }
    }

    async function loadCurrentDirectory(options = {}) {
        if (!state.currentRoot) return;
        if (state.loading && !options.force) return;
        state.loading = true;
        renderer.setStatus('正在读取目录内容...', '');
        try {
            const previousPath = state.currentPath;
            const payload = await fetchFileManagerList(ctx, state.currentRoot, state.currentPath);
            state.lastPayload = payload;
            state.currentPath = payload.directory || state.currentPath;
            if (!state.uploadTarget || state.uploadTarget === previousPath) {
                state.uploadTarget = state.currentPath;
            }
            state.entries = payload.entries || [];
            renderer.renderDirectory();
            renderer.setStatus(payload.message || `已读取 ${state.entries.length} 个条目。`, 'ok');
        } catch (error) {
            renderer.setStatus(`读取目录失败: ${error.message}`, 'error');
        } finally {
            state.loading = false;
        }
    }

    function bindFileManagerEvents() {
        document.getElementById('file-manager-root')?.addEventListener('change', (event) => {
            const rootId = event.target.value || '';
            const root = (state.roots || []).find((item) => item.id === rootId);
            state.currentRoot = rootId;
            state.currentPath = root?.path || '';
            loadCurrentDirectory({ force: true });
        });
        document.getElementById('btn-file-manager-go')?.addEventListener('click', () => {
            state.currentPath = document.getElementById('file-manager-path')?.value || state.currentPath;
            loadCurrentDirectory({ force: true });
        });
        document.getElementById('btn-file-manager-refresh')?.addEventListener('click', () => loadCurrentDirectory({ force: true }));
        document.getElementById('file-manager-path')?.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                state.currentPath = event.target.value || state.currentPath;
                loadCurrentDirectory({ force: true });
            }
        });
        document.getElementById('file-manager-search')?.addEventListener('input', (event) => {
            state.search = event.target.value || '';
            renderer.renderDirectory();
        });
        document.getElementById('file-manager-upload-target')?.addEventListener('input', (event) => {
            state.uploadTarget = event.target.value || '';
        });
        document.getElementById('btn-file-manager-upload')?.addEventListener('click', uploadSelectedFile);
        document.getElementById('file-manager-list')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-file-manager-action]');
            const row = event.target.closest('.file-manager-entry');
            if (!button || !row) return;
            const action = button.dataset.fileManagerAction || '';
            const entryPath = row.dataset.entryPath || '';
            const kind = row.dataset.entryKind || '';
            const isSymlink = row.dataset.entrySymlink === '1';
            if (action === 'open') {
                if (kind !== 'dir' || isSymlink) {
                    renderer.setStatus('符号链接目录暂不允许进入。', 'error');
                    return;
                }
                state.currentPath = entryPath;
                loadCurrentDirectory({ force: true });
                return;
            }
            if (action === 'download') {
                window.location.href = buildFileManagerDownloadUrl(state.currentRoot, entryPath);
                return;
            }
            if (action === 'extract') {
                planAndRunExtract(entryPath, state.currentPath);
                return;
            }
            if (action === 'rename') {
                renameCurrentEntry(entryPath);
            }
        });
    }

    async function uploadSelectedFile() {
        if (state.uploading) return;
        const fileInput = document.getElementById('file-manager-upload-input');
        const file = fileInput?.files?.[0];
        if (!file) {
            renderer.setStatus('请先选择一个本地文件。', 'error');
            return;
        }
        const targetPath = (state.uploadTarget || '').trim() || state.currentPath;
        if (!state.currentRoot || !targetPath) {
            renderer.setStatus('缺少上传目标目录。', 'error');
            return;
        }
        state.uploading = true;
        renderer.setUploadProgress(0, '准备上传...');
        renderer.setStatus(`正在上传到 ${targetPath} ...`, '');
        try {
            const payload = await uploadFileManagerFile(ctx, {
                root: state.currentRoot,
                targetPath,
                file,
                onProgress(progress) {
                    state.uploadProgress = progress.percent || 0;
                    renderer.setUploadProgress(
                        state.uploadProgress,
                        `上传进度 ${state.uploadProgress}% (${progress.loaded}/${progress.total})`,
                    );
                },
            });
            state.currentPath = targetPath;
            state.uploadTarget = targetPath;
            if (fileInput) fileInput.value = '';
            renderer.setUploadProgress(100, '上传完成');
            renderer.setStatus(
                payload.uploaded?.overwritten
                    ? `上传完成，已覆盖 ${payload.uploaded?.name || file.name}`
                    : `上传完成：${payload.uploaded?.name || file.name}`,
                'ok',
            );
            if (document.getElementById('file-manager-auto-extract')?.checked) {
                await planAndRunExtract(payload.uploaded?.path || `${targetPath}/${file.name}`, targetPath);
                return;
            }
            await loadCurrentDirectory({ force: true });
        } catch (error) {
            renderer.setStatus(`上传失败: ${error.message}`, 'error');
            renderer.setUploadProgress(state.uploadProgress || 0, '上传失败');
        } finally {
            state.uploading = false;
        }
    }

    async function planAndRunExtract(archivePath, targetDir) {
        if (!archivePath || !targetDir) {
            renderer.setStatus('缺少解压路径参数。', 'error');
            return;
        }
        try {
            const plan = await planFileManagerExtract(ctx, {
                root: state.currentRoot,
                archivePath,
                targetDir,
                overwrite: false,
            });
            if (plan.ok === false) {
                throw new Error(plan.error || '解压预检查失败');
            }
            const summary = plan.summary || {};
            const conflicts = plan.conflicts || [];
            const confirmMessage = [
                `即将解压 ${plan.archive?.name || archivePath}`,
                `目标目录: ${plan.target_dir || targetDir}`,
                `文件数: ${summary.files || 0}`,
                `目录数: ${summary.dirs || 0}`,
                `冲突数: ${summary.conflicts || 0}`,
                conflicts.length ? `冲突示例: ${conflicts.map((item) => item.member).join(', ')}` : '没有发现冲突',
                summary.conflicts ? '确认后将以覆盖模式继续解压。' : '确认后开始解压。',
            ].join('\n');
            const confirmed = window.confirm(confirmMessage);
            if (!confirmed) {
                renderer.setStatus('已取消解压。', '');
                return;
            }
            const started = await runFileManagerExtract(ctx, {
                root: state.currentRoot,
                archivePath,
                targetDir,
                overwrite: Boolean(summary.conflicts),
            });
            if (started.ok === false) {
                throw new Error(started.error || '启动解压失败');
            }
            state.extractJobId = started.job?.id || '';
            renderer.setStatus('已提交解压任务，正在等待完成...', '');
            await pollExtractJob(state.extractJobId);
            await loadCurrentDirectory({ force: true });
        } catch (error) {
            renderer.setStatus(`解压失败: ${error.message}`, 'error');
        }
    }

    async function pollExtractJob(jobId) {
        if (!jobId) return;
        while (true) {
            const payload = await fetchFileManagerJobStatus(ctx, jobId);
            const job = payload.job || {};
            renderer.setStatus(
                job.message || `解压任务状态: ${job.state || 'unknown'} (${job.current || 0}/${job.total || 0})`,
                job.state === 'error' ? 'error' : '',
            );
            if (job.state === 'done') {
                renderer.setStatus(`解压完成 (${job.current || 0}/${job.total || 0})`, 'ok');
                return;
            }
            if (job.state === 'error') {
                throw new Error(job.error || job.message || '解压任务失败');
            }
            await new Promise((resolve) => window.setTimeout(resolve, 1000));
        }
    }

    async function renameCurrentEntry(entryPath) {
        if (!entryPath) {
            renderer.setStatus('缺少重命名路径。', 'error');
            return;
        }
        const currentName = entryPath.split('/').filter(Boolean).pop() || '';
        const nextName = window.prompt('请输入新名称（仅同目录改名）', currentName);
        if (nextName == null) {
            renderer.setStatus('已取消重命名。', '');
            return;
        }
        const trimmed = String(nextName).trim();
        if (!trimmed || trimmed === currentName) {
            renderer.setStatus('新名称未变化。', '');
            return;
        }
        try {
            const payload = await renameFileManagerEntry(ctx, {
                root: state.currentRoot,
                path: entryPath,
                newName: trimmed,
            });
            renderer.setStatus(`已重命名为 ${payload.renamed?.new_path || trimmed}`, 'ok');
            await loadCurrentDirectory({ force: true });
        } catch (error) {
            renderer.setStatus(`重命名失败: ${error.message}`, 'error');
        }
    }

    return {
        bindFileManagerEvents,
        loadFileManagerRoots,
        loadCurrentDirectory,
    };
}
