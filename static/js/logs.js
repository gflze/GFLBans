const LOGS = Object.freeze({
    // Infraction
    EVENT_NEW_INFRACTION: 0,
    EVENT_REMOVE_INFRACTION: 1,
    EVENT_EDIT_INFRACTION: 2,
    EVENT_NEW_COMMENT: 3,
    EVENT_EDIT_COMMENT: 4,
    EVENT_DELETE_COMMENT: 5,
    EVENT_UPLOAD_FILE: 6,
    EVENT_DELETE_FILE: 7,
    EVENT_RPC_KICK: 8,

    // Server
    EVENT_NEW_SERVER: 8,
    EVENT_EDIT_SERVER: 9,

    // Group
    EVENT_SET_GROUP_PERMISSIONS: 10,
    EVENT_ADD_GROUP: 11,
    EVENT_DELETE_GROUP: 12,
    EVENT_SET_ADMIN_PERMISSIONS: 13,

    // VPN
    EVENT_NEW_VPN: 14,
    EVENT_DELETE_VPN: 15,
    EVENT_EDIT_VPN: 16,
});

const folderToEventTypes = {
    infraction: [
        LOGS.EVENT_NEW_INFRACTION,
        LOGS.EVENT_REMOVE_INFRACTION,
        LOGS.EVENT_EDIT_INFRACTION,
        LOGS.EVENT_NEW_COMMENT,
        LOGS.EVENT_EDIT_COMMENT,
        LOGS.EVENT_DELETE_COMMENT,
        LOGS.EVENT_UPLOAD_FILE,
        LOGS.EVENT_DELETE_FILE,
        LOGS.EVENT_RPC_KICK
    ],
    server: [
        LOGS.EVENT_NEW_SERVER,
        LOGS.EVENT_EDIT_SERVER
    ],
    group: [
        LOGS.EVENT_SET_GROUP_PERMISSIONS,
        LOGS.EVENT_ADD_GROUP,
        LOGS.EVENT_DELETE_GROUP,
        LOGS.EVENT_SET_ADMIN_PERMISSIONS
    ],
    vpn: [
        LOGS.EVENT_NEW_VPN,
        LOGS.EVENT_DELETE_VPN,
        LOGS.EVENT_EDIT_VPN
    ]
};

const logs2name = {};
logs2name[LOGS.EVENT_NEW_INFRACTION] = 'New Infraction';
logs2name[LOGS.EVENT_REMOVE_INFRACTION] = 'Remove Infraction';
logs2name[LOGS.EVENT_EDIT_INFRACTION] = 'Edit Infraction';
logs2name[LOGS.EVENT_NEW_COMMENT] = 'New Comment';
logs2name[LOGS.EVENT_DELETE_COMMENT] = 'Delete Comment';
logs2name[LOGS.EVENT_UPLOAD_FILE] = 'Upload File';
logs2name[LOGS.EVENT_DELETE_FILE] = 'Delete File';
logs2name[LOGS.EVENT_RPC_KICK] = 'RPC Kick';
logs2name[LOGS.EVENT_NEW_SERVER] = 'New Server';
logs2name[LOGS.EVENT_EDIT_SERVER] = 'Edit Server';
logs2name[LOGS.EVENT_SET_GROUP_PERMISSIONS] = 'Set Group Permissions';
logs2name[LOGS.EVENT_ADD_GROUP] = 'Add Group';
logs2name[LOGS.EVENT_DELETE_GROUP] = 'Delete Group';
logs2name[LOGS.EVENT_SET_ADMIN_PERMISSIONS] = 'Set Admin Permimssions';
logs2name[LOGS.EVENT_NEW_VPN] = 'New VPN';
logs2name[LOGS.EVENT_DELETE_VPN] = 'Delete VPN';
logs2name[LOGS.EVENT_EDIT_VPN] = 'Edit VPN';

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

$(document).ready(function () {
    LoadNewLogs();
    LoadAdminList();

    $('#logs-category div').on('click', function () {
        $('#logs-category div').removeClass('selected');
        $(this).addClass('selected');
        const type = $(this).val();
        LoadNewLogs();
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
            $('#logs-admin div').removeClass('selected');
            $(this).addClass('selected');
            const type = $(this).val();
            LoadNewLogs();
        })
    );

    adminList.append($('<div>')
        .addClass('admin-item')
        .attr('data-type', -1)
        .text('System')
        .prop('selected', true)
        .on('click', function () {
            $('#logs-admin div').removeClass('selected');
            $(this).addClass('selected');
            const type = $(this).val();
            LoadNewLogs();
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
            const type = $(this).val();
            LoadNewLogs();
        });

        adminList.append(el);
    }
}

function LoadNewLogs() {
    const start = new Date().getTime();
    setLoading();
    $('#logs-table-body').empty();
    const getAuditLogs = {
        limit: 30,
        skip: 0
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
            const errorData = response.json();
            throw new Error(errorData.detail || defaultAPIError);
        }

        response.json().then(data => {
            const dur = 200 - (new Date().getTime() - start);

            function _LoadNewLogs() {
                data.results.sort(function(a, b) {
                    return ((a['time'] < b['time']) ? -1 : ((a['time'] > b['time']) ? 1 : 0));
                });

                for (let i = 0; i < data.results.length; i++) {
                    const auditLog = data.results[i];

                    const row = $('<div>').addClass('logs-table-row');

                    if (auditLog.hasOwnProperty('time'))
                        row.append($('<div>').text(auditLog['time']));
                    else
                        row.append($('<div>').text('Unknown'));

                    if (auditLog.hasOwnProperty('event_type'))
                        row.append($('<div>').text(logs2name[auditLog['event_type']]));
                    else
                        row.append($('<div>').text('Unknown'));

                    if (auditLog.hasOwnProperty('authentication_type'))
                        row.append($('<div>').text(auth2name[auditLog['authentication_type']]));
                    else
                        row.append($('<div>').text('Unknown'));

                    if (auditLog.hasOwnProperty('authenticator'))
                        row.append($('<div>').text(auditLog['authenticator']));
                    else
                        row.append($('<div>').text('Unknown'));

                    if (auditLog.hasOwnProperty('admin'))
                        row.append($('<div>').text(auditLog['admin']));
                    else
                        row.append($('<div>').text('Unknown'));

                    /*
                    row.attr('data-group', group['group_id']);

                    row.click(function () {
                        openGroupMenu(this.getAttribute('data-group'));
                    });
                    */

                    $('#logs-table-body').append(row);
                }

                if (data.results.length === 0)
                    $('#logs-table-body')
                        .html($('<h1 style="text-align: center; font-size: 30pt;">No audit logs found</h1>'));

                unsetLoading();
            }

            if (dur > 0)
                setTimeout(_LoadNewLogs, dur);
            else
                _LoadNewLogs();
        });
    }).catch(e => {
        logException(e);
    });
}
