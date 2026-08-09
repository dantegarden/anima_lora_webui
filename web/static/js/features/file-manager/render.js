function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function formatSize(size) {
    const value = Number(size || 0);
    if (!Number.isFinite(value) || value <= 0) return '0 B';
    if (value >= 1024 ** 3) return `${(value / (1024 ** 3)).toFixed(2)} GB`;
    if (value >= 1024 ** 2) return `${(value / (1024 ** 2)).toFixed(1)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${Math.round(value)} B`;
}

function formatMtime(value) {
    if (!value) return '-';
    const date = new Date(Number(value) * 1000);
    return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString();
}

function isExtractableArchive(entry) {
    const name = String(entry?.name || '').toLowerCase();
    return name.endsWith('.tar') || name.endsWith('.tar.gz') || name.endsWith('.tgz') || name.endsWith('.zip');
}

export function createFileManagerRenderer({ state }) {
    function renderRoots() {
        const select = document.getElementById('file-manager-root');
        if (!select) return;
        select.innerHTML = (state.roots || []).map((root) => `
            <option value="${escapeHtml(root.id)}"${root.id === state.currentRoot ? ' selected' : ''}>
                ${escapeHtml(root.label)}
            </option>
        `).join('');
    }

    function renderDirectory() {
        const uploadTarget = document.getElementById('file-manager-upload-target');
        if (uploadTarget && !state.uploading) {
            uploadTarget.value = state.uploadTarget || '';
        }
        const pathInput = document.getElementById('file-manager-path');
        if (pathInput) pathInput.value = state.currentPath || '';
        const breadcrumb = document.getElementById('file-manager-breadcrumb');
        if (breadcrumb) breadcrumb.textContent = state.currentPath || '-';
        const list = document.getElementById('file-manager-list');
        if (!list) return;
        const search = String(state.search || '').trim().toLowerCase();
        const entries = (state.entries || []).filter((entry) => {
            if (!search) return true;
            return String(entry.name || '').toLowerCase().includes(search);
        });
        const availablePaths = new Set((state.entries || [])
            .filter((entry) => !entry.is_symlink)
            .map((entry) => entry.path));
        state.selectedPaths = new Set([...state.selectedPaths].filter((path) => availablePaths.has(path)));
        updateSelectionControls();
        if (!entries.length) {
            list.innerHTML = '<div class="file-manager-empty">当前目录没有可显示的条目。</div>';
            return;
        }
        list.innerHTML = entries.map((entry) => `
            <div class="file-manager-entry" data-entry-path="${escapeHtml(entry.path)}" data-entry-kind="${escapeHtml(entry.kind)}" data-entry-symlink="${entry.is_symlink ? '1' : '0'}">
                <input class="file-manager-entry-select" type="checkbox" aria-label="选择 ${escapeHtml(entry.name)}" data-file-manager-select${state.selectedPaths.has(entry.path) ? ' checked' : ''}${entry.is_symlink ? ' disabled' : ''}>
                <div class="file-manager-entry-main">
                    <strong>${escapeHtml(entry.name)}</strong>
                    <span>${entry.kind === 'dir' ? '目录' : '文件'}${entry.is_symlink ? ' · 符号链接' : ''}</span>
                </div>
                <div class="file-manager-entry-meta">
                    <span>${escapeHtml(formatSize(entry.size))}</span>
                    <span>${escapeHtml(formatMtime(entry.mtime))}</span>
                </div>
                <div class="file-manager-entry-actions">
                    ${entry.kind === 'dir' ? '<button class="btn btn-small" type="button" data-file-manager-action="open">进入</button>' : ''}
                    ${!entry.is_symlink ? '<button class="btn btn-small" type="button" data-file-manager-action="rename">重命名</button>' : ''}
                    ${entry.kind === 'file' && !entry.is_symlink && isExtractableArchive(entry) ? '<button class="btn btn-small" type="button" data-file-manager-action="extract">解压</button>' : ''}
                    ${!entry.is_symlink ? '<button class="btn btn-small btn-subtle-danger" type="button" data-file-manager-action="delete">删除</button>' : ''}
                    ${entry.kind === 'file' ? '<button class="btn btn-small btn-primary" type="button" data-file-manager-action="download">下载</button>' : ''}
                </div>
            </div>
        `).join('');
    }

    function updateSelectionControls() {
        const button = document.getElementById('btn-file-manager-delete-selected');
        const count = state.selectedPaths.size;
        if (button) {
            button.disabled = count === 0;
            button.textContent = count ? `删除所选 (${count})` : '删除所选';
        }
    }

    function setStatus(message, tone = '') {
        const status = document.getElementById('file-manager-status');
        if (!status) return;
        status.className = `file-manager-status ${tone || ''}`.trim();
        status.textContent = message || '';
    }

    function setUploadProgress(percent = 0, message = '') {
        const progress = document.getElementById('file-manager-upload-progress');
        const label = document.getElementById('file-manager-upload-progress-text');
        if (progress) {
            progress.value = Number(percent || 0);
            progress.hidden = Number(percent || 0) <= 0 && !state.uploading;
        }
        if (label) {
            label.textContent = message || '';
        }
    }

    return {
        renderRoots,
        renderDirectory,
        updateSelectionControls,
        setStatus,
        setUploadProgress,
    };
}
