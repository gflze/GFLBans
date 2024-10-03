const MGMT = Object.freeze({
    ADMIN: 0,
    GROUP: 1,
    SERVER: 2,
    APIKEY: 3
});

let MGMT_MODE = 0;

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

    setLoading();
    let mode = $('html').attr('data-mode');

    if (mode === 'GROUP') {
        MGMT_MODE = MGMT.GROUP;
        $('#mgmt-add').click(function(){openGroupMenu(0)});
    } else if (mode === 'SERVER') {
        MGMT_MODE = MGMT.SERVER;
        $('#mgmt-add').click(function(){openServerMenu(0)});
    } else if (mode === 'APIKEY') {
        MGMT_MODE = MGMT.APIKEY;
        $('#mgmt-table').html($('<div style="text-align: center; font-size: 40pt">WORK IN PROGRESS</div>'));
        unsetLoading();
        return;
    }
    else {
        MGMT_MODE = MGMT.ADMIN;
        $('#mgmt-add').click(function(){openAdminMenu(0)});
    }

    loadMgmt(start);
});


// Stuff for adding database obejcts to main list on page
function loadMgmt(start) {
    $('#mgmt-table > tbody').empty();
    let endpoint = '';
    switch(MGMT_MODE) {
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

    gbRequest('GET', endpoint, null).then(function (response) {
        handleResponse(response, start);
    }).catch(err => {
        console.log(err);
        showError();
    });
}

function handleResponse(response, start) {
    if (!response.ok) {
        throw 'Received Not-OK response from the API';
    }

    response.json().then(data => {
        let dur = 200 - (new Date().getTime() - start);

        function _loadMgmt() {
            switch(MGMT_MODE) {
                case MGMT.GROUP:
                    var addRow = addGroupRow;
                    data.sort(sortGroups);
                    break;
                case MGMT.SERVER:
                    var addRow = addServerRow;
                    data.sort(function(a, b) {
                        // Put disabled servers at bottom
                        if (!a.hasOwnProperty('enabled') && !b.hasOwnProperty('enabled'))
                            return 0;
                        else if (!a.hasOwnProperty('enabled'))
                            return 1;
                        else if (!b.hasOwnProperty('enabled'))
                            return -1;
                        else if (a['enabled'] !== b['enabled'])
                            return a['enabled'] ? -1 : 1;
                        
                        let aName = a.hasOwnProperty('group_name') ? a['group_name'].toLowerCase() : 'unnamed server';
                        let bName = b.hasOwnProperty('group_name') ? b['group_name'].toLowerCase() : 'unnamed server';
                        return ((aName < bName) ? -1 : ((aName > bName) ? 1 : 0));
                    });
                    break;
                case MGMT.ADMIN:
                default:
                    var addRow = addAdminRow;
                    data.sort(function(a, b) {
                        let aName = a.hasOwnProperty('admin_name') ? a['admin_name'].toLowerCase() : 'unnamed admin';
                        let bName = b.hasOwnProperty('admin_name') ? b['admin_name'].toLowerCase() : 'unnamed admin';
                        return ((aName < bName) ? -1 : ((aName > bName) ? 1 : 0));
                    });
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
    let row = $('<tr>').addClass('mgmt-item admin-row');

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

    admin['groups'].sort(sortGroups);
    for (let i = 0; i < admin['groups'].length; i++) {
        if (admin['groups'][i].hasOwnProperty('group_name'))
            group_list.append($('<li>').text(admin['groups'][i]['group_name']));
        else
            group_list.append($('<li>').text('Unnamed Group'));
    }

    row.append(identity_cell);
    row.append(group_cell);

    row.attr('data-admin', admin['admin_id']);
    
    row.click(function () {
        openAdminMenu(this.getAttribute('data-admin'));
    });

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

    row.attr('data-group', group['group_id']);
    
    row.click(function () {
        openGroupMenu(this.getAttribute('data-group'));
    });

    $('#mgmt-table > tbody').append(row);
}

function addServerRow(server) {
    let row = $('<tr>').addClass('mgmt-item server-row');

    // Enabled
    let enabled_cell = $('<td>').addClass('vertical-center has-text-centered is-hidden-mobile');
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
    ip_cell.text('Unset IP');
    if (server.hasOwnProperty('ip')) { // Check for no IP added (manual mongodb entry)
        ip_cell.text(server['ip']);
        if (server.hasOwnProperty('game_port'))
            ip_cell.text(ip_cell.text() + ':' + server['game_port']);
    }
    row.append(enabled_cell);
    row.append(name_cell);
    row.append(ip_cell);

    row.attr('data-server', server['id']);
    
    row.click(function () {
        openServerMenu(this.getAttribute('data-server'));
    });

    $('#mgmt-table > tbody').append(row);
}

function sortGroups(a, b) {
    let aName = a.hasOwnProperty('group_name') ? a['group_name'].toLowerCase() : 'unnamed group';
    let bName = b.hasOwnProperty('group_name') ? b['group_name'].toLowerCase() : 'unnamed group';
    return ((aName < bName) ? -1 : ((aName > bName) ? 1 : 0));
}

function getFlagsFromBitFlag(bitFlag) {
    let base2 = (bitFlag).toString(2);
    let bitFlags = [];
    for (let i = 0; i < base2.length; i++)
        if (base2[i] === '1') bitFlags.push(1 << (base2.length - i - 1));
    return bitFlags;
}



// Stuff for adding/editing/deleting an admin in database
function openAdminMenu(adminID = 0) {
    if ($('#mgmt-add').hasClass('is-loading'))
        return;
    $('#mgmt-add').addClass('is-loading');

    loadAdminMenu(adminID).catch(function (e) {
       console.log(e);
       showError('An error occurred. Please try reloading the page or contact the host if the problem persists.')
   });
}

async function loadAdminMenu(adminID) {
    resetAdminMenu();
    group_list = [];
    if (adminID === 0) {
        $('#steamIdEntry').prop('disabled', false);
        $('#manageDelete').addClass('is-hidden');
        $('.modal-card-title').text('Create Admin');
        $('#manageSubmit').text('Add Admin');
    } else {
        let adminInfo = await gbRequest('GET', '/api/admin/?admin_id=' + adminID, null);
        if (!adminInfo.ok) {
            throw adminInfo.error();
        }
        let admin = await adminInfo.json();
        admin = admin[0];
        $('#manageDelete').removeClass('is-hidden');

        // Use existing admin identity
        $('#nameEntry').val(admin.hasOwnProperty('admin_name') ? admin['admin_name'] : '');
        $('#steamIdEntry').val('U:1:' + adminID);
        $('#steamIdEntry').prop('disabled', true);

        for (let i = 0; i < admin['groups'].length; i++) {
            group_list.push(admin['groups'][i]['group_id']);
        }

        $('.modal-card-title').text('Update ' + (admin.hasOwnProperty('admin_name') ? admin['admin_name'] : 'Admin'));
        $('#manageSubmit').text('Update ' + (admin.hasOwnProperty('admin_name') ? admin['admin_name'] : 'Admin'));
        $('#manageDelete').click(deleteAdmin);
    }
    
    closeModals();

    //Setup groups
    let groupsRequest = await gbRequest('GET', '/api/group/', null);

    if (!groupsRequest.ok) {
        throw groupsRequest.error();
    }

    let groups = await groupsRequest.json()
    groups.sort(sortGroups);
    let groupButtons = $('#groupButtons');

    groupButtons.empty()

    for (let i = 0; i < groups.length; i++) {
        let classes = 'gbtn button';
        if (!group_list.includes(groups[i]['group_id']))
            classes = 'gbtn button is-outlined';

        if (groups[i].hasOwnProperty('group_name')) // Check for no name added (messed up manual mongodb entry)
            groupButtons.append($('<button>').addClass(classes).text(groups[i]['group_name']).val(groups[i]['group_id']));
        else
            groupButtons.append($('<button>').addClass(classes).text('Unnamed Group').val(groups[i]['group_id']));
    }

    $('.gbtn').click(function (ev) {
        toggleButton(ev.target);
    })

    //Setup and show the error AddMenu
    $('#createAddMenu').addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');

    $('#mgmt-add').removeClass('is-loading');

    $('.manageDismiss').off('click').click(function () {
        resetAdminMenu();
        closeModals();
    });

    $('.cDismissError').click(function () {
        $('#createError').addClass('is-hidden');
    })

    $('#manageSubmit').click(submitNewAdmin)
}

function resetAdminMenu() {
    $('#mgmt-add').removeClass('is-loading');
    $('#createError').addClass('is-hidden');

    // Default admin identity
    $('#nameEntry').val('');
    $('#steamIdEntry').val('');
}

function toggleButton(target) {
    let t = $(target)

    console.log(t);

    if (t.hasClass('ricon')) {
        if (t.hasClass('icon')) {
            toggleButton(target.parentNode);
            return;
        } else if (t.hasClass('fas')) {
            toggleButton(target.parentNode);
            return;
        }
    }

    if (t.hasClass('is-outlined')) {
        t.removeClass('is-outlined');
    } else {
        t.addClass('is-outlined');
    }

    console.log(t);
}

function submitNewAdmin() {
    setLoading()

    // First request
    let adminCall = createAndValidateAdmin();

    //Failure, the second index is the error
    if (!adminCall[0]) {
        $('#createErrorMsg').text(adminCall[1]);
        $('#createError').removeClass('is-hidden');
        unsetLoading();
        return;
    }

    //Success, the second index is the request type and the third is the actual request struct

    let route = '/api/admin/'

    gbRequest('PUT', route, adminCall[1], true).then(handleAdminSubmission).catch(function (e) {
        console.log(e);
        showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
    })
}

function deleteAdmin() {
    setLoading();

    // First request
    if ($('#steamIdEntry').val().trim().length === 0) {
        $('#createErrorMsg').text('You must enter a Steam64 ID.');
        $('#createError').removeClass('is-hidden');
        unsetLoading();
        return;
    }

    let admin = {
        'admin_id': $('#steamIdEntry').val().trim(),
        'groups': [] // 'Deleting' an admin is just emptying their groups
    };

    let route = '/api/admin/';

    gbRequest('PUT', route, admin, true).then(handleAdminSubmission).catch(function (e) {
        console.log(e);
        showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
    })
}

function handleAdminSubmission(resp) {
    if (!resp.ok) {
        console.log(resp);
        resp.text().then(function (t) {
            console.log(t)
        })
        throw 'Server returned a non-OK error code.'
    }

    closeModals();
    window.location.reload();
}

function createAndValidateAdmin() {
    let admin = {
        'groups': []
    };

    if ($('#nameEntry').val().trim() !== '')
        admin['admin_name'] = $('#nameEntry').val().trim();
    else
        return [false, 'You must enter a name.'];

    if ($('#steamIdEntry').val().trim() !== '')
        admin['admin_id'] = $('#steamIdEntry').val().trim();
    else
        return [false, 'You must enter a Steam64 ID.']

    $('.gbtn:not(.is-outlined)').each(function(i, obj) {
        admin['groups'].push($(obj).val());
    });

    if (admin['groups'].length === 0)
        return [false, 'You must select at least 1 group.'];

    return [true, admin];
}


// Stuff for adding/editing/deleting a group in database
function openGroupMenu(groupID = 0) {
    if ($('#mgmt-add').hasClass('is-loading'))
        return;
    $('#mgmt-add').addClass('is-loading');

    loadGroupMenu(groupID).catch(function (e) {
       console.log(e);
       showError('An error occurred. Please try reloading the page or contact the host if the problem persists.')
   });
}

async function loadGroupMenu(groupID) {
    resetGroupMenu();
    permission_list = [];
    if (groupID === 0) {
        $('.modal-card-title').text('Create Group');
        $('#manageSubmit').text('Add Group');
        $('#manageDelete').addClass('is-hidden');
    } else {
        let groupInfo = await gbRequest('GET', '/api/group/' + groupID, null);
        if (!groupInfo.ok) {
            throw groupInfo.error();
        }
        let group = await groupInfo.json();
        $('#manageDelete').removeClass('is-hidden');

        // Use existing group identity
        $('#nameEntry').val(group.hasOwnProperty('group_name') ? group['group_name'] : '');
        permission_list = getFlagsFromBitFlag(group['permissions']);

        $('.modal-card-title').text('Update ' + (group.hasOwnProperty('group_name') ? group['group_name'] : 'Group'));
        $('#manageSubmit').text('Update ' + (group.hasOwnProperty('group_name') ? group['group_name'] : 'Group'));

        $('#manageSubmit').attr('data-group', groupID);
        $('#manageDelete').click(deleteGroup);
    }
    
    closeModals();

    // Setup permissions
    let permissionButtons = $('#permissionButtons');

    permissionButtons.empty();

    for (let [flag, name] of Object.entries(perms2name)) {
        let classes = 'gbtn button';
        if (!permission_list.includes(Number(flag)))
            classes = 'gbtn button is-outlined';

        permissionButtons.append($('<button>').addClass(classes).text(name).val(flag));
    }

    $('.gbtn').click(function (ev) {
        toggleButton(ev.target);
    })

    //Setup and show the error AddMenu
    $('#createAddMenu').addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');

    $('#mgmt-add').removeClass('is-loading');

    $('.manageDismiss').off('click').click(function () {
        resetGroupMenu();
        closeModals();
    });

    $('.cDismissError').click(function () {
        $('#createError').addClass('is-hidden');
    })

    $('#manageSubmit').click(submitGroupChange)
}

function resetGroupMenu() {
    $('#mgmt-add').removeClass('is-loading');
    $('#createError').addClass('is-hidden');
    $('#manageSubmit').removeAttr('data-group');

    // Default group identity
    $('#nameEntry').val('');
}

function submitGroupChange() {
    setLoading();

    let groupID = $('#manageSubmit').attr('data-group');

    // First request
    let groupCall = createAndValidateGroup();

    // Failure, the second index is the error
    if (!groupCall[0]) {
        $('#createErrorMsg').text(groupCall[1]);
        $('#createError').removeClass('is-hidden');
        unsetLoading();
        return;
    }

    if (typeof groupID === 'undefined' || groupID === false) {
        // Adding new group
        let route = '/api/group/';
        gbRequest('POST', route, groupCall[1], true).then(handleGroupSubmission).catch(function (e) {
            console.log(e);
            showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
        })
    } else {
        // Patching existing group
        let route = '/api/group/' + groupID;
        gbRequest('PATCH', route, groupCall[1], true).then(handleGroupSubmission).catch(function (e) {
            console.log(e);
            showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
        })
    }
}

function deleteGroup() {
    setLoading();
    let groupID = $('#manageSubmit').attr('data-group');

    // First request
    if (typeof groupID === 'undefined' || groupID === false) {
        $('#createErrorMsg').text('Something went wrong. This group does not have an associated group_id.');
        $('#createError').removeClass('is-hidden');
        unsetLoading();
        return;
    }

    let route = '/api/group/' + groupID;

    gbRequest('DELETE', route, null, true).then(handleGroupSubmission).catch(function (e) {
        console.log(e);
        showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
    })
}

function handleGroupSubmission(resp) {
    if (!resp.ok) {
        console.log(resp);
        resp.text().then(function (t) {
            console.log(t)
        })
        throw 'Server returned a non-OK error code.'
    }

    closeModals();
    window.location.reload();
}

function createAndValidateGroup() {
    let group = {};

    if ($('#nameEntry').val().trim() !== '')
        group['name'] = $('#nameEntry').val().trim();
    else
        return [false, 'You must enter a name.'];

    group['privileges'] = 0;
    $('.gbtn:not(.is-outlined)').each(function(i, obj) {
        group['privileges'] |= Number($(obj).val());
    });

    return [true, group];
}


// Stuff for adding/editing/deleting a server in database
function openServerMenu(serverID = 0) {
    if ($('#mgmt-add').hasClass('is-loading'))
        return;
    $('#mgmt-add').addClass('is-loading');

    loadServerMenu(serverID).catch(function (e) {
       console.log(e);
       showError('An error occurred. Please try reloading the page or contact the host if the problem persists.')
   });
}

async function loadServerMenu(serverID) {
    resetServerMenu();
    if (serverID === 0) {
        $('.modal-card-title').text('Create Server');
        $('#manageSubmit').text('Add Server');
        $('#manageDelete').addClass('is-hidden');
    } else {
        let serverInfo = await gbRequest('GET', '/api/server/' + serverID, null);
        if (!serverInfo.ok) {
            throw serverInfo.error();
        }
        let server = await serverInfo.json();
        $('#generateToken').removeClass('is-hidden');
        $('#manageDelete').removeClass('is-hidden');

        if (server['enabled'])
            $('#manageDelete').removeClass('is-success').addClass('is-danger').text('Disable');
        else
            $('#manageDelete').removeClass('is-danger').addClass('is-success').text('Enable');

        // Use existing server identity
        $('#nameEntry').val(server.hasOwnProperty('friendly_name') ? server['friendly_name'] : '');
        $('#ipEntry').val(server.hasOwnProperty('ip') ? server['ip'] : '');
        $('#portEntry').val(server.hasOwnProperty('game_port') ? Number(server['game_port']) : '');

        $('.modal-card-title').text('Update ' + (server.hasOwnProperty('friendly_name') ? server['friendly_name'] : 'Server'));
        $('#manageSubmit').text('Update Server');

        $('#manageSubmit').attr('data-server', serverID);
        $('#manageDelete').click(toggleServer);

        $('#generateToken').click(function (ev) {
            toggleButton(ev.target);
        })
    }
    
    closeModals();

    //Setup and show the error AddMenu
    $('#createAddMenu').addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');

    $('#mgmt-add').removeClass('is-loading');

    $('.manageDismiss').off('click').click(function () {
        resetServerMenu();
        closeModals();
    });

    $('.cDismissError').click(function () {
        $('#createError').addClass('is-hidden');
    })

    $('#manageSubmit').click(submitServerChange)
}

function resetServerMenu() {
    $('#mgmt-add').removeClass('is-loading');
    $('#createError').addClass('is-hidden');
    $('#generateToken').addClass('is-hidden');
    $('#manageSubmit').removeAttr('data-server');

    // Default server identity
    $('#nameEntry').val('');
    $('#ipEntry').val('');
    $('#portEntry').val('');
    $('#calladminEntry').val('');
    $('#infractionEntry').val('');
    $('#roleIDEntry').val('');
}

async function submitServerChange() {
    setLoading();

    let serverID = $('#manageSubmit').attr('data-server');

    // First request
    let serverCall = createAndValidateServer();

    // Failure, the second index is the error
    if (!serverCall[0]) {
        $('#createErrorMsg').text(serverCall[1]);
        $('#createError').removeClass('is-hidden');
        unsetLoading();
        return;
    }

    if (typeof serverID === 'undefined' || serverID === false) {
        // Adding new server
        serverCall[1]['enabled'] = true;
        let route = '/api/server/';
        let serverInfo = await gbRequest('POST', route, serverCall[1], true);

        if (!serverInfo.ok) {
            console.log(e);
            showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
            return;
        }

        showNewToken(await serverInfo.json());
        
        //gbRequest('POST', route, serverCall[1], true).then(handleServerSubmissionNewToken).catch(function (e) {
        //    console.log(e);
        //    showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
        //});
    } else {
        // Patching existing server
        let route = '/api/server/' + serverID;
        if (!$('#generateToken').hasClass('is-outlined')) {
            let serverInfo = await gbRequest('PATCH', route, serverCall[1], true);

            if (!serverInfo.ok) {
                console.log(e);
                showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
                return;
            }

            //gbRequest('PATCH', route, serverCall[1], true).then(handleServerSubmissionDoublePatch).catch(function (e) {
            //    console.log(e);
            //    showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
            //});

            route = route + '/token';
            serverInfo = await gbRequest('GET', route, null, true);

            if (!serverInfo.ok) {
                console.log(e);
                showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
                return;
            }

            showNewToken(await serverInfo.json());

            //gbRequest('GET', route, null, true).then(handleServerSubmissionNewToken).catch(function (e) {
            //    console.log(e);
            //    showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
            //});
        } else {
            gbRequest('PATCH', route, serverCall[1], true).then(handleServerSubmission).catch(function (e) {
                console.log(e);
                showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
            });
        }
    }
}

function toggleServer() {
    setLoading();
    let serverID = $('#manageSubmit').attr('data-server');

    if (typeof serverID === 'undefined' || serverID === false) {
        $('#createErrorMsg').text('Something went wrong. This server does not have an associated id.');
        $('#createError').removeClass('is-hidden');
        unsetLoading();
        return;
    }

    let server = {};
    server['enabled'] = $('#manageDelete').hasClass('is-success');
    let route = '/api/server/' + serverID;

    // We disable servers rather than deleting so we dont mess up infractions tied to them
    gbRequest('PATCH', route, server, true).then(handleServerSubmission).catch(function (e) {
        console.log(e);
        showError('An error occurred. Please try reloading the page or contact the host if the problem persists.');
    })
}

function handleServerSubmission(resp) {
    if (!resp.ok) {
        console.log(resp);
        resp.text().then(function (t) {
            console.log(t)
        })
        throw 'Server returned a non-OK error code.'
    }

    closeModals();
    window.location.reload();
}

function handleServerSubmissionDoublePatch(resp) {
    if (!resp.ok) {
        console.log(resp);
        resp.text().then(function (t) {
            console.log(t)
        })
        throw 'Server returned a non-OK error code.'
    }
}

function showNewToken(serverInfo) {
    closeModals();

    //Setup and show the error modal
    $('.modal-card-title').text('CS2Fixes Convars');
    $('#setupURL').text(window.location.host + '/api/');
    if (serverInfo.hasOwnProperty('server'))
        $('#setupID').text(serverInfo['server']);
    else
        $('#setupID').text($('#manageSubmit').attr('data-server'));

    $('#setupkey').text(serverInfo['server_secret_key']);

    $('#setupClipboard').click(function () {
        let text = '';
        $('#setupModal section p').each(function(i, obj) {
            let convar = $(obj);
            text = text + convar.text() + '\n';
        });
        navigator.clipboard.writeText(text);
    });

    $('#setupModal').addClass('is-active');
    $('#htmlRoot').addClass('is-clipped');

    $(".modal-background").click(function () {
        closeModals();
        window.location.reload();
    });
}

function createAndValidateServer() {
    let server = {};

    if ($('#nameEntry').val().trim() !== '')
        server['friendly_name'] = $('#nameEntry').val().trim();
    else
        return [false, 'You must enter a name.'];

    let ip = $('#ipEntry').val().trim();
    if (ip !== '' && /^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$/.test(ip))
        server['ip'] = ip;
    else
        return [false, 'You must enter a valid IP Address.'];

    if ($('#portEntry').val().trim() !== '')
        server['game_port'] = $('#portEntry').val().trim();
    else
        return [false, 'You must enter a port.'];

    if ($('#calladminEntry').val().trim() !== '' && $('#roleIDEntry').val().trim() !== '') {
        server['discord_webhook'] = $('#calladminEntry').val().trim();
        server['discord_staff_tag'] = $('#roleIDEntry').val().trim();
    } else if (($('#calladminEntry').val().trim() !== '' || $('#roleIDEntry').val().trim() !== ''))
        return [false, 'You must give either both discord_webhook and discord_staff_tag or neither.'];

    return [true, server];
}