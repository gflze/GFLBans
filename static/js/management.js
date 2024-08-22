const MGMT = Object.freeze({
    ADMIN: 0,
    GROUP: 1,
    SERVER: 2,
    APIKEY: 3
});

const PERMISSION = Object.freeze({
    LOGIN: 1 << 0, // Login to the website
    COMMENT: 1 << 1,
    VIEW_IP_ADDR: 1 << 2,
    CREATE_INFRACTION: 1 << 3,
    EDIT_OWN_INFRACTIONS: 1 << 4, // Deprecated, all admins with PERMISSION.CREATE_INFRACTION can edit their own punishments.
    EDIT_ALL_INFRACTIONS: 1 << 5,
    ATTACH_FILE: 1 << 6,
    WEB_MODERATOR: 1 << 7, // Can edit or delete comments/files on infractions
    MANAGE_SERVERS: 1 << 8,
    MANAGE_VPNS: 1 << 9,
    PRUNE_INFRACTIONS: 1 << 10,
    VIEW_AUDIT_LOG: 1 << 11,
    MANAGE_GROUPS_AND_ADMINS: 1 << 12,
    MANAGE_API_KEYS: 1 << 13,
    ACP_BLOCK_EDITOR: 1 << 14, // Deprecated
    BLOCK_VOICE: 1 << 15,  // Add voice blocks to infractions
    BLOCK_CHAT: 1 << 16,  // Add chat blocks to infractions
    BAN: 1 << 17,  // Add bans to infractions
    ADMIN_CHAT_BLOCK: 1 << 18,  // Block admin chat
    CALL_ADMIN_BLOCK: 1 << 19,  // Block call admin usage
    SCOPE_SUPER_GLOBAL: 1 << 20,  // Admin can use SUPER GLOBAL infractions
    SCOPE_GLOBAL: 1 << 21,  // Admins can use GLOBAL infractions
    VPN_CHECK_SKIP: 1 << 22,  // Users with this permission are immune to VPN kicks
    MANAGE_POLICY: 1 << 23,  // Manage tiering policies
    IMMUNE: 1 << 24,  // Immune from bans
    SKIP_IMMUNITY: 1 << 25,  // Overrides immunity
    RPC_KICK: 1 << 26,
    ASSIGN_TO_SERVER: 1 << 27,  // Assign an infraction to a specific server
    MANAGE_MAP_ICONS: 1 << 28  // Upload and delete map icons
});

let perms2name = {};
perms2name[PERMISSION.LOGIN] = 'Can Login';
perms2name[PERMISSION.COMMENT] = 'Can Comment';
perms2name[PERMISSION.VIEW_IP_ADDR] = 'Can See IP Addresses';
perms2name[PERMISSION.CREATE_INFRACTION] = 'Add Infractions';
perms2name[PERMISSION.EDIT_OWN_INFRACTIONS] = 'DEPRECATED, DO NOT GIVE';
perms2name[PERMISSION.EDIT_ALL_INFRACTIONS] = 'Edit All Infractions';
perms2name[PERMISSION.ATTACH_FILE] = 'Attach Files';
perms2name[PERMISSION.WEB_MODERATOR] = 'Panel Admin';
perms2name[PERMISSION.MANAGE_SERVERS] = 'Manage Servers';
perms2name[PERMISSION.MANAGE_VPNS] = 'Manage VPNs';
perms2name[PERMISSION.PRUNE_INFRACTIONS] = 'Prune Infractions';
perms2name[PERMISSION.VIEW_AUDIT_LOG] = 'View Audit Log';
perms2name[PERMISSION.MANAGE_GROUPS_AND_ADMINS] = 'Manage Groups and Admins';
perms2name[PERMISSION.MANAGE_API_KEYS] = 'Manage API Keys';
perms2name[PERMISSION.ACP_BLOCK_EDITOR] = 'DEPRECATED, DO NOT GIVE';
perms2name[PERMISSION.BLOCK_VOICE] = 'Restrict Voice';
perms2name[PERMISSION.BLOCK_CHAT] = 'Restrict Text';
perms2name[PERMISSION.BAN] = 'Ban';
perms2name[PERMISSION.ADMIN_CHAT_BLOCK] = 'Restrict Admin Chat';
perms2name[PERMISSION.CALL_ADMIN_BLOCK] = 'Restrict Call Admin';
perms2name[PERMISSION.SCOPE_SUPER_GLOBAL] = 'Add Community Infractions';
perms2name[PERMISSION.SCOPE_GLOBAL] = 'Add Global Infractions';
perms2name[PERMISSION.VPN_CHECK_SKIP] = 'VPN Kick Immunity';
perms2name[PERMISSION.MANAGE_POLICY] = 'Manage Tiering Policies';
perms2name[PERMISSION.IMMUNE] = 'Immune from Bans';
perms2name[PERMISSION.SKIP_IMMUNITY] = 'Overrides Immunity';
perms2name[PERMISSION.RPC_KICK] = 'RPC Kick';
perms2name[PERMISSION.ASSIGN_TO_SERVER] = 'Assign an Infraction to a Specific Server';
perms2name[PERMISSION.MANAGE_MAP_ICONS] = 'Upload and Delete Map Icons';

$(document).ready(function () {
    let start = new Date().getTime();
    let url = window.location.href.toUpperCase();

    setLoading();
    
    if (url.includes('GROUP'))
        loadMgmt(start, MGMT.GROUP);
    else if (url.includes('SERVER'))
        loadMgmt(start, MGMT.SERVER);
    else if (url.includes('APIKEY')) {
        $('#mgmt-table').html('');
        $('#mgmt-table').append($('<div style="text-align: center; font-size: 80pt">WORK IN PROGRESS</div>'));
        unsetLoading();
    }
    else
        loadMgmt(start, MGMT.ADMIN);
});

function loadMgmt(start, type) {
    let endpoint = '';
    switch(type) {
        case MGMT.GROUP:
            endpoint = '/api/group'
            break;
        case MGMT.SERVER:
            endpoint = '/api/server'
            break;
        case MGMT.ADMIN:
        default:
            endpoint = '/api/admin';
            break;
    }

    $('#mgmt-table > tbody').html(''); // Clear out table

    gbRequest('GET', endpoint, null).then(function (response) {
        handleResponse(response, start, type);
    }).catch(err => {
        console.log(err);
        showError();
    });
}

function handleResponse(response, start, type) {
    if (!response.ok) {
        throw 'Received Not-OK response from the API';
    }

    response.json().then(data => {
        let dur = 200 - (new Date().getTime() - start);

        function _loadMgmt() {
            switch(type) {
                case MGMT.GROUP:
                    var addRow = addGroupRow;
                    break;
                case MGMT.SERVER:
                    var addRow = addServerRow;
                    break;
                case MGMT.ADMIN:
                default:
                    var addRow = addAdminRow;
                    break;
            }

            for (let i = 0; i < data.length; i++) {
                addRow(data[i]);
            }

            if (data.length === 0) {
                setupEmptyNotice();
            }

            unsetLoading();
        }

        if (dur > 0) {
            setTimeout(_loadMgmt, dur);
        } else {
            _loadMgmt();
        }
    });
}

function setupEmptyNotice() {

    let i_root = document.getElementById('infractions_tab');

    $(i_root).empty();

    i_root.classList.add('has-text-centered')
    i_root.classList.remove('table-container');

    let icon = document.createElement('i');
    icon.classList.add('fas', 'fa-question', 'mt-5', 'nf-icon');

    let text = document.createElement('h1');
    text.innerText = 'No Infractions';
    text.classList.add('is-size-1');

    let subtext = document.createElement('p');
    subtext.innerText = 'Your query matched no documents. Try a different search or add an infraction using the hammer icon in the top-left corner.';
    subtext.classList.add('mb-5');

    i_root.appendChild(icon);
    i_root.appendChild(text);
    i_root.appendChild(subtext);
}

function addAdminRow(admin) {
    let row = $('<tr>').addClass('mgmt-item');

    // Picture + Name
    let identity_cell = $('<td>').addClass('vertical-center has-text-left');

    let identity_image = $('<img>').addClass('mgmt-admin-av mr-2').attr('src', '/static/images/fallback_av.png');
    identity_cell.append(identity_image);

    let identity_name = $('<span>').text('Unnamed Admin');
    identity_cell.append(identity_name);

    if (admin.hasOwnProperty('admin_name')) // Check for no name added (messed up manual mongodb entry)
        identity_name.text(admin['admin_name']);
    if (admin.hasOwnProperty('avatar_id'))
        identity_image.attr('src', '/file/uploads/' + admin['avatar_id'] + '/avatar.webp');

    // Groups
    let group_cell = $('<td>').addClass('vertical-center has-text-centered');

    let group_list = $('<ul>').addClass('group-list');

    group_cell.append(group_list);

    for (let i = 0; i < admin['groups'].length; i++) {
        group_list.append($('<li>').text(admin['groups'][i]['group_name']));
    }

    row.append(identity_cell);
    row.append(group_cell);

    /* Click to edit admin view
    row.setAttribute('data-admin', admin['admin_id']);

    row.click(function () {
        openAdmin(row.getAttribute('data-admin'));
    });
    */

    $('#mgmt-table > tbody').append(row);
}

function addGroupRow(group) {
    let row = $('<tr>').addClass('mgmt-item group-row');

    // Name
    let name_cell = $('<td>').addClass('vertical-center has-text-centered').text('Unnamed Group');

    if (group.hasOwnProperty('group_name')) // Check for no name added (messed up manual mongodb entry)
        name_cell.text(group['group_name']);

    // Permissions
    let perms_cell = $('<td>').addClass('vertical-center has-text-left');

    let perms_list = $('<ol>').addClass('permission-list');

    perms_cell.append(perms_list);
    if (!group.hasOwnProperty('permissions') || group['permissions'] === 0)
        perms_list.append($('<li>').text('NONE'));
    else {
        let perms = getFlagsFromBitFlag(group['permissions']);
        for (let i = 0; i < perms.length; i++) {
            perms_list.append($('<li>').text(perms2name[perms[i]]));
        }
    }

    row.append(name_cell);
    row.append(perms_cell);

    /* Click to edit group view
    row.setAttribute('data-group', group['admin_id']);

    row.click(function () {
        openGroup(row.getAttribute('data-group'));
    });
    */

    $('#mgmt-table > tbody').append(row);
}

function addServerRow(server) {
    let row = $('<tr>').addClass('mgmt-item group-row');

    // Enabled
    let enabled_cell = $('<td>').addClass('vertical-center has-text-centered');
    let enabled_icon = $('<i>').addClass('fas fa-question-circle');
    if (server.hasOwnProperty('enabled')) {
        enabled_icon.removeClass('fa-question-circle');
        if (server['enabled'])
            enabled_icon.addClass('fas fa-check-circle');
        else
            enabled_icon.addClass('fas fa-minus-circle');
    }
    enabled_cell.append(enabled_icon);

    // Name
    let name_cell = $('<td>').addClass('vertical-center has-text-centered').text('Unnamed Server');

    if (server.hasOwnProperty('friendly_name')) // Check for no name added (manual mongodb entry)
        name_cell.text(server['friendly_name']);

    // IP
    let ip_cell = $('<td>').addClass('vertical-center has-text-centered');
    ip_cell.text('Unknown IP');
    if (server.hasOwnProperty('ip')) { // Check for no name added (manual mongodb entry)
        ip_cell.text(server['ip']);
        if (server.hasOwnProperty('game_port'))
            ip_cell.text(ip_cell.text() + ':' + server['game_port']);
    }
    row.append(enabled_cell);
    row.append(name_cell);
    row.append(ip_cell);

    /* Click to edit server view
    row.setAttribute('data-server', group['id']);

    row.click(function () {
        openServer(row.getAttribute('data-server'));
    });
    */

    $('#mgmt-table > tbody').append(row);
}

function getFlagsFromBitFlag(bitFlag) {
    let base2 = (bitFlag).toString(2);
    let bitFlags = [];
    for (let i = 0; i < base2.length; i++)
        if (base2[i] === '1') bitFlags.push(1 << i);
    return bitFlags;
}