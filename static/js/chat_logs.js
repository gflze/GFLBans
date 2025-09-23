let CHATLOGS_LIMIT = 80;
let oldestMessageTimestamp = null;
let reachedEnd = false; // true when we've scrolled to end
let isLoading = false;
let existingMessages = [];

function toUnix(dtStr) {
    if (!dtStr)
        return 0;
    const d = new Date(dtStr);
    if (isNaN(d.getTime()))
        return 0;
    return Math.floor(d.getTime() / 1000);
}

async function loadServersIntoFilter() {
    try {
        const resp = await gbRequest('GET', '/api/server/?enabled_only=false');
        if (!resp.ok)
            throw new Error(defaultAPIError);

        const data = await resp.json();
        const sel = document.getElementById('filter-server');
        for (const s of data) {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = s.friendly_name
                ? `${s.friendly_name} (${s.ip}:${s.game_port})`
                : `${s.ip}:${s.game_port}`;
            sel.appendChild(opt);
        }

        // Auto-select the first server if available and load
        if (data.length > 0) {
            sel.value = data[0].id;
            resetAndLoad();
        }
    } catch (e) {
        logException(e);
    }
}

function buildQuery(isLoadingOlder = false) {
    const serverId = document.getElementById('filter-server').value;
    const search = document.getElementById('filter-search').value.trim();
    const content = document.getElementById('filter-content').value.trim();
    const created_after = toUnix(document.getElementById('filter-after').value);
    const created_before = toUnix(document.getElementById('filter-before').value);
    const command_mode = document.getElementById('filter-command-mode').value;

    const q = {
        limit: CHATLOGS_LIMIT,
        sort_desc: true
    };

    if (isLoadingOlder && oldestMessageTimestamp) {
        q['created_before'] = oldestMessageTimestamp;
    } else if (created_before > 0) {
        q['created_before'] = created_before;
    }

    if (search.length > 0)
        q['search'] = search;
    if (content.length > 0)
        q['content'] = content;
    if (created_after > 0)
        q['created_after'] = created_after;
    if (command_mode && command_mode !== 'all')
        q['command_mode'] = command_mode;

    return { q, serverId };
}

function getAuthorKey(message) {
    return (message.user && message.user.gs_service && message.user.gs_id)
        ? (message.user.gs_service + ':' + message.user.gs_id)
        : 'unknown';
}

function getGroupAuthorKey(groupElement) {
    const firstMessageElement = groupElement.querySelector('.chat-message');
    if (!firstMessageElement)
        return null;

    return groupElement.getAttribute('data-author-key');
}

// Compact message group like Discord: avatar+name once, then stacked messages
function renderMessageGroup(user, messages) {
    const wrapper = document.createElement('div');
    wrapper.classList.add('is-flex', 'mb-2');

    // Store the author key for later comparison during infinite scroll
    const authorKey = getAuthorKey(messages[0]);
    wrapper.setAttribute('data-author-key', authorKey);

    const avatar = document.createElement('img');
    avatar.classList.add('mr-2', 'avatar', 'set-default-on-error');
    if (user && user.gs_avatar)
        avatar.src = '/file/uploads/' + user.gs_avatar.file_id + '/avatar.webp';
    else
        avatar.src = '/static/images/fallback_av.png';

    const right = document.createElement('div');
    right.classList.add('is-flex-grow-1');

    // Header: name + timestamp of first msg
    const header = document.createElement('div');
    header.classList.add('is-flex', 'is-align-items-baseline');
    const nameEl = document.createElement('strong');
    const displayName = (user && user.gs_name) ? user.gs_name : 'Unknown Player';
    const profileUrl = user ? getProfileUrl(user) : null;
    if (profileUrl) {
        const a = document.createElement('a');
        a.href = '#';
        a.textContent = displayName;
        a.onclick = function () {
            openLinkInNewTab(profileUrl); return false;
        };
        nameEl.appendChild(a);
    } else {
        nameEl.textContent = displayName;
    }
    const timeEl = document.createElement('span');
    timeEl.classList.add('is-size-7', 'ml-2');
    timeEl.textContent = new Date(messages[0].created * 1000).toLocaleString();
    header.appendChild(nameEl);
    header.appendChild(timeEl);

    right.appendChild(header);

    let allowHammer = false;
    try {
        const perms = parseInt(getMeta('active_permissions'));
        allowHammer = Boolean((perms & PERMISSION.CREATE_INFRACTION) && (perms & PERMISSION.BLOCK_CHAT));
    } catch (e) { /* ignore */ }

    for (const m of messages) {
        const row = document.createElement('div');
        row.classList.add('is-flex', 'is-align-items-center', 'mt-1', 'chat-message');

        if (allowHammer && m.id) {
            const hammer = document.createElement('button');
            hammer.classList.add('button', 'is-small', 'chat-message-hammer');
            const icon = document.createElement('i');
            icon.classList.add('fas', 'fa-gavel');
            hammer.appendChild(icon);
            hammer.title = 'Punish';
            hammer.onclick = function (ev) {
                ev.stopPropagation();
                openQuickPunish(user, m);
            };
            row.appendChild(hammer);

            row.addEventListener('mouseenter', () => {
                hammer.style.display = 'inline-flex';
            });
            row.addEventListener('mouseleave', () => {
                hammer.style.display = 'none';
            });
        }

        const content = document.createElement('div');
        content.classList.add('is-size-7');
        content.textContent = m.content;
        row.appendChild(content);
        right.appendChild(row);
    }

    wrapper.appendChild(avatar);
    wrapper.appendChild(right);
    return wrapper;
}

function openQuickPunish(user, message) {
    // Reset and open base modal
    loadModal().then(() => {
        $('#gameIdEntry').closest('.field').addClass('is-hidden');
        $('#ipEntry').closest('.field').addClass('is-hidden');
        let ctxEl = document.getElementById('chatlogContext');
        if (!ctxEl) {
            ctxEl = document.createElement('div');
            ctxEl.id = 'chatlogContext';
            ctxEl.classList.add('notification', 'is-info');
            const targetServerField = document.getElementById('targetServerField');
            targetServerField.parentNode.insertBefore(ctxEl, targetServerField);
        }
        ctxEl.innerText = `${user.gs_name || 'Unknown Player'}: ${message.content}`;

        const serverId = document.getElementById('filter-server').value;
        if (serverId) {
            $('#serverSelector').val(serverId).prop('disabled', true);
        }

        $('#isWebToggle').prop('checked', false).prop('disabled', true).addClass('is-hidden');
        $('#targetServerField').show();

        const voiceBtn = $('#restrictVoice');
        const textBtn = $('#restrictText');
        const banBtn = $('#restrictJoin');
        const adminChatBtn = $('#restrictAdminChat');
        const callAdminBtn = $('#restrictCallAdmin');
        const itemBtn = $('#restrictItem');

        [voiceBtn, textBtn, banBtn, adminChatBtn, callAdminBtn, itemBtn].forEach(btn => {
            if (btn.length)
                btn.addClass('is-outlined');
        });

        [voiceBtn, banBtn, adminChatBtn, callAdminBtn, itemBtn].forEach(btn => {
            if (btn.length)
                btn.addClass('is-hidden');
        });

        if (textBtn.length)
            textBtn.removeClass('is-outlined');

        // Lock the punishment checkboxes except toggling among warn/text/silence
        // We will manage three radio-like choices:
        // Create three buttons under the header for quick selection
        const bar = $('<div class="buttons are-small mt-2"></div>');
        const warnBtn = $('<button class="button is-light">Warn</button>');
        const textPresetBtn = $('<button class="button is-accent is-light">Text</button>');
        const silenceBtn = $('<button class="button is-light">Silence</button>');
        function setMode(mode) {
            // Reset
            if (textBtn.length)
                textBtn.addClass('is-outlined');
            if (voiceBtn.length)
                voiceBtn.addClass('is-outlined');
            warnBtn.removeClass('is-accent');
            textPresetBtn.removeClass('is-accent');
            silenceBtn.removeClass('is-accent');
            if (mode === 'warn') {
                warnBtn.addClass('is-accent');
            } else if (mode === 'text') {
                if (textBtn.length)
                    textBtn.removeClass('is-outlined');
                textPresetBtn.addClass('is-accent');
            } else if (mode === 'silence') {
                if (textBtn.length)
                    textBtn.removeClass('is-outlined');
                if (voiceBtn.length)
                    voiceBtn.removeClass('is-outlined');
                silenceBtn.addClass('is-accent');
            }
        }
        warnBtn.on('click', () => setMode('warn'));
        textPresetBtn.on('click', () => setMode('text'));
        silenceBtn.on('click', () => setMode('silence'));
        setMode('text');
        $('#cTypeHeader').after(bar.append(warnBtn, textPresetBtn, silenceBtn));

        // Disable unrelated inputs
        $('#durationEntry').prop('disabled', false); // allow duration choice
        $('#unitSelector').prop('disabled', false);

        // Override submit to call secure chatlog endpoint (backend fetches SteamID/IP)
        $('#cInfractionSubmit').off('click').on('click', function () {
            const reason = $('#reasonEntry').val().trim();
            if (reason.length === 0) {
                $('#infractionCreateErrorMsg').text('You must enter a reason!');
                $('#infractionCreateError').removeClass('is-hidden');
                return;
            }
            let preset = 'text';
            if (voiceBtn.length && !voiceBtn.hasClass('is-outlined'))
                preset = 'silence';
            if (textBtn.length
                && textBtn.hasClass('is-outlined')
                && voiceBtn.length
                && voiceBtn.hasClass('is-outlined'))
                preset = 'warn';

            const payload = {
                chatlog_id: message.id,
                preset: preset,
                reason: reason,
                auto_duration: $('#autoStackCheck').prop('checked'),
                playtime_based: $('#timeDecCheck').prop('checked'),
                permanent: $('#permanentCheck').prop('checked')
            };

            if (
                ($('#globalCheck').prop('checked'))
                && $('#globalCheck').attr('data-has-permissions') === '1'
            )
                payload['scope'] = 'global';
            else
                payload['scope'] = 'server';

            if (!payload.auto_duration && !payload.permanent) {
                try {
                    payload.duration = getInfractionSeconds();
                } catch (e) {
                    $('#infractionCreateErrorMsg').text(e);
                    $('#infractionCreateError').removeClass('is-hidden');
                    return;
                }
            }

            gbRequest('POST', '/api/infractions/chatlog', payload, true)
                .then(handleInfractionSubmission)
                .catch(logException);
        });
    }).catch(logException);
}

function setLoading() {
    $('#chatlogs-list').addClass('is-loading');
}
function unsetLoading() {
    $('#chatlogs-list').removeClass('is-loading');
}

function resetAndLoad() {
    const container = document.getElementById('chatlogs-list');
    container.innerHTML = '';
    oldestMessageTimestamp = null;
    reachedEnd = false;
    isLoading = false;
    existingMessages = [];
    loadMore(false, true);
}

function loadMore(append=true, scrollToBottom=false) {
    if (isLoading || reachedEnd)
        return;

    isLoading = true;
    setLoading();

    const { q, serverId } = buildQuery(append);
    if (!serverId || serverId.length === 0) {
        unsetLoading();
        isLoading = false;
        return;
    }

    gbRequest('GET', `/api/server/${serverId}/logs?` + new URLSearchParams(q).toString(), null, true)
        .then(resp => {
            if (!resp.ok) {
                throw new Error(resp.json().detail || defaultAPIError);
            }

            resp.json().then(data => {
                if (data.length < CHATLOGS_LIMIT)
                    reachedEnd = true;

                if (data.length > 0) {
                    const oldestMsg = data[data.length - 1];
                    oldestMessageTimestamp = oldestMsg.created;
                }

                let container = document.getElementById('chatlogs-list');
                if (!append)
                    container.innerHTML = '';

                // Capture the current scroll position and height before making changes
                let prevScrollTop = container.scrollTop;
                let prevScrollHeight = container.scrollHeight;

                const renderBatch = (items) => {
                    let group = [];
                    let lastKey = null;
                    let firstMessageCreated = 9999999999;
                    function flush(target, grp) {
                        if (grp.length === 0)
                            return;
                        const user = grp[0].user || null;
                        target.appendChild(renderMessageGroup(user, grp));
                    }

                    // Sort by created date to ensure oldest messages are at the top
                    const chronologicalItems = [...items].sort((a, b) => a.created - b.created);

                    for (const m of chronologicalItems) {
                        const key = getAuthorKey(m);
                        if (lastKey === null || (m.created < (firstMessageCreated + 300) && key === lastKey)) {
                            if (group.length === 0)
                                firstMessageCreated = m.created

                            group.push(m);
                            lastKey = key;
                        } else {
                            flush(container, group);
                            group = [m];
                            lastKey = key;
                            firstMessageCreated = m.created
                        }
                    }
                    flush(container, group);
                };

                if (!append) {
                    renderBatch(data);
                    existingMessages = [...data].sort((a, b) => a.created - b.created);
                    if (scrollToBottom) {
                        container.scrollTop = container.scrollHeight;
                    }
                } else {
                    let shouldMerge = false;
                    let mergeGroups = [];

                    if (existingMessages.length > 0 && data.length > 0) {
                        const oldestExistingAuthorKey = getAuthorKey(existingMessages[0]); // Oldest in existing data

                        // Check if any message in the new batch has the same author as the oldest existing message
                        for (const message of data) {
                            const messageAuthorKey = getAuthorKey(message);
                            if (messageAuthorKey
                                && oldestExistingAuthorKey
                                && messageAuthorKey === oldestExistingAuthorKey) {
                                shouldMerge = true;
                                break;
                            }
                        }
                    }

                    if (shouldMerge) {
                        const mergedData = [...data, ...existingMessages];
                        existingMessages = mergedData.sort((a, b) => a.created - b.created);

                        container.innerHTML = '';
                        renderBatch(mergedData);
                    } else {
                        const frag = document.createDocumentFragment();

                        const temp = document.createElement('div');
                        const originalContainer = container;
                        container = temp;
                        renderBatch(data);
                        while (temp.firstChild)
                            frag.appendChild(temp.firstChild);
                        originalContainer.insertBefore(frag, originalContainer.firstChild);
                        container = originalContainer;

                        existingMessages = [...data, ...existingMessages].sort((a, b) => a.created - b.created);
                    }

                    // Maintain scroll offset so content appears to grow upwards
                    const newScrollHeight = container.scrollHeight;
                    const heightDifference = newScrollHeight - prevScrollHeight;
                    container.scrollTop = prevScrollTop + heightDifference;
                }

                isLoading = false;
                unsetLoading();
            });
        })
        .catch(e => {
            logException(e);
            isLoading = false;
            unsetLoading();
        });
}

$(document).ready(function () {
    loadServersIntoFilter();

    $('#chatlogs-list').on('scroll', function () {
        const el = this;
        if (el.scrollTop <= 10)
            loadMore(true);
    });

    $('#filter-apply').on('click', function () {
        resetAndLoad();
    });
});
