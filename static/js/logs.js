const LOGS = Object.freeze({
    // Infraction
    EVENT_INFRACTION_NEW: 0,
    EVENT_INFRACTION_REMOVE: 1,
    EVENT_INFRACTION_EDIT: 2,
    EVENT_COMMENT_NEW: 3,
    EVENT_COMMENT_EDIT: 4,
    EVENT_COMMENT_DELETE: 5,
    EVENT_FILE_UPLOAD: 6,
    EVENT_FILE_DELETE: 7,
    EVENT_RPC_KICK: 17,

    // Server
    EVENT_SERVER_NEW: 8,
    EVENT_SERVER_EDIT: 9,
    EVENT_SERVER_REGENERATE_TOKEN: 18,

    // Group
    EVENT_PERMISSIONS_GROUP_EDIT: 10,
    EVENT_PERMISSIONS_GROUP_ADD: 11,
    EVENT_PERMISSIONS_GROUP_DELETE: 12,
    EVENT_PERMISSIONS_ADMIN_EDIT: 13,

    // VPN
    EVENT_VPN_NEW: 14,
    EVENT_VPN_DELETE: 15,
    EVENT_VPN_EDIT: 16,
});

const folderToEventTypes = {
    infraction: [
        LOGS.EVENT_INFRACTION_NEW,
        LOGS.EVENT_INFRACTION_REMOVE,
        LOGS.EVENT_INFRACTION_EDIT,
        LOGS.EVENT_COMMENT_NEW,
        LOGS.EVENT_COMMENT_EDIT,
        LOGS.EVENT_COMMENT_DELETE,
        LOGS.EVENT_FILE_UPLOAD,
        LOGS.EVENT_FILE_DELETE,
        LOGS.EVENT_RPC_KICK
    ],
    server: [
        LOGS.EVENT_SERVER_NEW,
        LOGS.EVENT_SERVER_EDIT,
        LOGS.EVENT_SERVER_REGENERATE_TOKEN
    ],
    group: [
        LOGS.EVENT_PERMISSIONS_GROUP_EDIT,
        LOGS.EVENT_PERMISSIONS_GROUP_ADD,
        LOGS.EVENT_PERMISSIONS_GROUP_DELETE,
        LOGS.EVENT_PERMISSIONS_ADMIN_EDIT
    ],
    vpn: [
        LOGS.EVENT_VPN_NEW,
        LOGS.EVENT_VPN_DELETE,
        LOGS.EVENT_VPN_EDIT
    ]
};

const logs2name = {};
logs2name[LOGS.EVENT_INFRACTION_NEW] = 'New Infraction';
logs2name[LOGS.EVENT_INFRACTION_REMOVE] = 'Remove Infraction';
logs2name[LOGS.EVENT_INFRACTION_EDIT] = 'Edit Infraction';
logs2name[LOGS.EVENT_COMMENT_NEW] = 'New Comment';
logs2name[LOGS.EVENT_COMMENT_EDIT] = 'Edit Comment';
logs2name[LOGS.EVENT_COMMENT_DELETE] = 'Delete Comment';
logs2name[LOGS.EVENT_FILE_UPLOAD] = 'Upload File';
logs2name[LOGS.EVENT_FILE_DELETE] = 'Delete File';
logs2name[LOGS.EVENT_RPC_KICK] = 'RPC Kick';
logs2name[LOGS.EVENT_SERVER_NEW] = 'New Server';
logs2name[LOGS.EVENT_SERVER_EDIT] = 'Edit Server';
logs2name[LOGS.EVENT_SERVER_REGENERATE_TOKEN] = 'Regenerate Server Token';
logs2name[LOGS.EVENT_PERMISSIONS_GROUP_EDIT] = 'Set Group Permissions';
logs2name[LOGS.EVENT_PERMISSIONS_GROUP_ADD] = 'Add Group';
logs2name[LOGS.EVENT_PERMISSIONS_GROUP_DELETE] = 'Delete Group';
logs2name[LOGS.EVENT_PERMISSIONS_ADMIN_EDIT] = 'Set Admin Permissions';
logs2name[LOGS.EVENT_VPN_NEW] = 'New VPN';
logs2name[LOGS.EVENT_VPN_DELETE] = 'Delete VPN';
logs2name[LOGS.EVENT_VPN_EDIT] = 'Edit VPN';

const AUTH_TYPE = Object.freeze({
    SERVER_KEY: 0,
    API_KEY: 1,
    AUTHED_USER: 2,
    NOT_AUTHED_USER: 3,
});

const auth2name = {};
auth2name[AUTH_TYPE.SERVER_KEY] = 'Server';
auth2name[AUTH_TYPE.API_KEY] = 'API Key';
auth2name[AUTH_TYPE.AUTHED_USER] = 'User';
auth2name[AUTH_TYPE.NOT_AUTHED_USER] = 'Unauthenticated';

// For infinite scroll of audit logs
let currentOffset = 0;
let reachedEnd = false;
let isLoading = false;
const LOGS_LIMIT = 50;

function ResetAndLoadLogs(el) {
    currentOffset = 0;
    reachedEnd = false;
    LoadNewLogs(false);
}

$(document).ready(function () {
    LoadNewLogs();
    LoadAdminList();

    $('#logs-category div').on('click', function () {
        $('#logs-category .selected').removeClass('selected');
        $(this).addClass('selected');
        ResetAndLoadLogs();
    });

    $('#logs-table-body').on('scroll', function () {
        const el = $(this).get(0);
        if (el.scrollTop + el.clientHeight >= el.scrollHeight - 10) {
            LoadNewLogs(true);
        }
    });
});

async function LoadAdminList() {
    const admins_req = await gbRequest('GET', '/api/admin/', null);

    if (!admins_req.ok) {
        logException(admins_req.error());
        return;
    }

    const admins = await admins_req.json();

    admins.sort(function(a, b) {
        if (!a.hasOwnProperty('admin_name'))
            return -1;
        else if (!b.hasOwnProperty('admin_name'))
            return 1;
        const aName = a['admin_name'].toLowerCase();
        const bName = b['admin_name'].toLowerCase();
        return ((aName < bName) ? -1 : ((aName > bName) ? 1 : 0));
    });

    const adminList = $('#logs-admin');
    adminList.empty();

    adminList.append($('<div>')
        .addClass('admin-folder selected')
        .attr('data-type', 0).text('All Admins')
        .prop('selected', true)
        .on('click', function () {
            $('#logs-admin .selected').removeClass('selected');
            $(this).addClass('selected');
            ResetAndLoadLogs();
        })
    );

    adminList.append($('<div>')
        .addClass('admin-item')
        .attr('data-type', -1)
        .text('System')
        .prop('selected', true)
        .on('click', function () {
            $('#logs-admin .selected').removeClass('selected');
            $(this).addClass('selected');
            ResetAndLoadLogs();
        })
    );

    for (let i = 0; i < admins.length; i++) {
        if (admins[i]['permissions'] <= 0)
            continue;
        const el = $('<div>').addClass('admin-item');
        if (admins[i]['admin_id'])
            el.attr('data-type', admins[i]['admin_id']);

        if (admins[i].hasOwnProperty('admin_name'))
            el.text(admins[i]['admin_name']);
        else
            el.text(admins[i]['admin_id']);

        el.on('click', function () {
            $('#logs-admin div').removeClass('selected');
            $(this).addClass('selected');
            ResetAndLoadLogs();
            LoadNewLogs();
        });

        adminList.append(el);
    }
}

function LoadNewLogs(append = false) {
    if (isLoading || reachedEnd) return;
    isLoading = true;

    const start = new Date().getTime();
    if (!append) {
        $('#logs-table-body').empty();
        $('#diff-viewer-container').empty().addClass('is-hidden');
        currentOffset = 0;
        reachedEnd = false;
    }

    setLoading();

    const getAuditLogs = {
        limit: LOGS_LIMIT,
        skip: currentOffset
    };

    const selectedCat = $('#logs-category .selected');
    const selectedType = selectedCat.data('type');

    if (selectedType !== 'all') {
        if (selectedType in folderToEventTypes) {
            getAuditLogs['event_type'] = folderToEventTypes[selectedType];
        } else if (selectedType in LOGS) {
            getAuditLogs['event_type'] = [LOGS[selectedType]];
        }
    }

    const selectedAdmin = $('#logs-admin .selected');
    const selectedAdminID = selectedAdmin.data('type');
    if (selectedAdminID != 0)
        getAuditLogs['admin'] = selectedAdminID;

    gbRequest('POST', '/api/logs/', getAuditLogs, true).then(function (response) {
        if (!response.ok) {
            throw new Error(response.json().detail || defaultAPIError);
        }

        response.json().then(data => {
            const dur = 200 - (new Date().getTime() - start);

            function _ProcessLogs() {
                if (data.results.length < LOGS_LIMIT) {
                    reachedEnd = true;
                }

                currentOffset += data.results.length;

                data.results.sort((a, b) => b['time'] - a['time']);

                if (!append && data.results.length === 0) {
                    $('#logs-table-body')
                        .html($('<h1 style="text-align: center; font-size: 30pt;">No audit logs found</h1>'));
                }

                for (const auditLog of data.results) {
                    const row = $('<div>').addClass('logs-table-row');
                    row.append($('<div>').text(auditLog.time ? moment.unix(auditLog.time).format('LLL') : 'Unknown'));
                    row.append($('<div>').text(logs2name[auditLog.event_type] ?? 'Unknown'));
                    row.append($('<div>').text(auditLog.admin ?? 'Unknown'));
                    row.append($('<div>').text(auth2name[auditLog.authentication_type] ?? 'Unknown'));
                    row.append($('<div>').text(auditLog.authenticator ?? 'Unknown'));

                    row.data('oldItem', auditLog.old_item || null);
                    row.data('newItem', auditLog.new_item || null);

                    row.on('click', function () {
                        $('.logs-table-row.selected').removeClass('selected');
                        $(this).addClass('selected');
                        const oldItem = $(this).data('oldItem');
                        const newItem = $(this).data('newItem');
                        let diff;

                        if (oldItem && newItem) {
                            diff = renderJsonDiff(oldItem, newItem);
                        } else if (oldItem) {
                            diff = renderJsonSingle(oldItem, '', false);
                        } else if (newItem) {
                            diff = renderJsonSingle(newItem, '', true);
                        } else {
                            diff = '<p class="diff-line diff-unchanged">No item data available</p>';
                        }

                        $('#diff-viewer-container').html(diff).removeClass('is-hidden');
                    });

                    $('#logs-table-body').append(row);
                }

                unsetLoading();
                isLoading = false;

                function isScrollableDown(el) {
                    return el.scrollHeight > el.clientHeight;
                }

                // ✅ Check if we need to load more because content doesn't overflow yet
                const bodyEl = $('#logs-table-body').get(0);
                if (!reachedEnd && !isScrollableDown(bodyEl)) {
                    LoadNewLogs(true);
                }
            }

            if (dur > 0)
                setTimeout(_ProcessLogs, dur);
            else
                _ProcessLogs();
        });
    }).catch(e => {
        logException(e);
        isLoading = false;
        unsetLoading();
    });
}


function renderJsonDiff(oldObj, newObj) {
    const output = [];

    function diff(o, n, prefix = '') {
        const keys = new Set([...Object.keys(o || {}), ...Object.keys(n || {})]);

        for (const key of Array.from(keys).sort()) {
            const oldVal = o?.[key];
            const newVal = n?.[key];
            const path = prefix ? `${prefix}.${key}` : key;

            const oldIsObj = typeof oldVal === 'object' && oldVal !== null;
            const newIsObj = typeof newVal === 'object' && newVal !== null;

            if (oldIsObj || newIsObj) {
                diff(oldIsObj ? oldVal : {}, newIsObj ? newVal : {}, path);
            } else if (JSON.stringify(oldVal) === JSON.stringify(newVal)) {
                output.push(`<p class="diff-line diff-unchanged">${path}: ${JSON.stringify(newVal)}</p>`);
            } else {
                if (oldVal !== undefined) {
                    output.push(`<p class="diff-line diff-remove">${path}: ${JSON.stringify(oldVal)}</p>`);
                }
                if (newVal !== undefined) {
                    output.push(`<p class="diff-line diff-add">${path}: ${JSON.stringify(newVal)}</p>`);
                }
            }
        }
    }

    diff(oldObj, newObj);
    return output.join('\n');
}

function renderJsonSingle(jsonObj, prefix = '', isNew = true) {
    const output = [];

    function recurse(obj, path) {
        for (const key of Object.keys(obj)) {
            const val = obj[key];
            const fullPath = path ? `${path}.${key}` : key;

            if (val && typeof val === 'object' && !Array.isArray(val)) {
                recurse(val, fullPath);
            } else {
                const displayVal = JSON.stringify(val);
                output.push(
                    `<p class="diff-line ${isNew ? 'diff-add' : 'diff-remove'}"> ${fullPath}: ${displayVal}</p>`
                );
            }
        }
    }

    recurse(jsonObj, prefix);
    return output.join('\n');
}
