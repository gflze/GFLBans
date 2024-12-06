$(document).ready(function () {
    $('#search-scope-web-check').click(handleWebCheck);
    $('#search-time-session-check').click(handleSessionCheck);
    $('#search-time-permanent-check').click(handlePermanentCheck);
    $('#search-time-game-timed-check').click(handleGameTimeCheck);
    $('#search-admin-admin-check').click(clickedAdminCheck);
    $('#advancedSearchToggle').click(openSearchModal);

    $('#search-admin-demoted-check').click(function() {
        $('#search-admin-info').removeClass('is-hidden');
        $('#search-admin-field').addClass('is-hidden'); 
    });

    $('#search-admin-system-check').click(function() {
        $('#search-admin-info').addClass('is-hidden');
        $('#search-admin-field').addClass('is-hidden');
    });

    $('.restriction-button').click(function (ev) {
        toggleRestriction(ev.target);
    });

    $('#search-admin-name').on('input', function () {
        if ($(this).val().trim() !== '') {
            $('#search-admin-id').addClass('is-hidden');
        } else {
            $('#search-admin-id').removeClass('is-hidden');
        }
    });

    $('#search-admin-id').on('input', function () {
        if ($(this).val().trim() !== '') {
            $('#search-admin-name').addClass('is-hidden');
        } else {
            $('#search-admin-name').removeClass('is-hidden');
        }
    });

    $('#advanced-search-modal .input').on('keypress', function(event) {
        if (event.which === 13)
            document.getElementById("search-submit").click();
    }); 
});

function resetSearchModal() {
    // User
    $('#search-user-vpn-check').prop('checked', false);
    $('#search-user-name').val('');
    $('#search-user-gsid').val('');
    $('#search-user-service-selector').val('steam');
    $('#search-user-ip').val('');

    // Admin
    $('[name="admin-type"]').prop('checked', false);
    $('#search-admin-admin-check').prop('checked', true);
    clickedAdminCheck();
    $('#search-admin-name').val('');
    $('#search-admin-name').removeClass('is-hidden');
    $('#search-admin-id').val('');
    $('#search-admin-id').removeClass('is-hidden');

    // Scope
    $('#search-scope-web-check').prop('checked', false);
    handleWebCheck();
    $('#search-scope-server-check').prop('disabled', false);
    $('#search-scope-server-label').removeClass('is-hidden');
    $('[name="scope-type"]').prop('checked', false);
    $('#search-scope-any-check').prop('checked', true);

    // Reasons
    $('#search-reason-creation').val('');
    $('#search-reason-removal').val('');

    // Restriction Types
    $('#search-restriction-warning').prop('checked', false);
    $('.restriction-button').addClass('is-outlined');

    // Time/Duration
    $('#search-time-session-check').prop('checked', false);
    handleSessionCheck();
    $('#search-time-permanent-check').prop('checked', false);
    handlePermanentCheck();
    $('#search-time-game-timed-check').prop('checked', false);
    handleGameTimeCheck();
    $('#search-time-duration-compare-selector').val('=');
    $('#search-time-duration-entry').val('');
    $('#search-time-duration-unit-selector').val('h');
    $('#search-time-timeleft-compare-selector').val('=');
    $('#search-time-timeleft-entry').val('');
    $('#search-time-timeleft-unit-selector').val('h');
    $('#search-perm-check-field').removeClass('is-hidden');
    $('#search-game-timed-check-field').removeClass('is-hidden');
    $('#search-time-duration-field').removeClass('is-hidden');

    $('#search-time-date-creation').val('');
    $('#search-time-date-creation-compare-selector').val('=');
    $('#search-time-date-expiration-compare-selector').val('=');

    // Status
    $('[name="status-type"]').prop('checked', false);
    $('#search-status-any-check').prop('checked', true);

    // Search Button
    $('#search-submit').off('click');
}

function handleWebCheck() {
    if ($('#search-scope-web-check').prop('checked')) {
        $('#search-scope-server-check').prop('disabled', true);
        $('#search-scope-server-label').attr('disabled', '1');
        $('#search-server-field').addClass('is-hidden');

        if ($('#search-scope-server-check').prop('checked')) {
            $('#search-scope-server-check').prop('checked', false);
            $('#search-scope-any-check').prop('checked', true);
        }
    } else {
        $('#search-scope-server-check').prop('disabled', false);
        $('#search-scope-server-label').removeAttr('disabled');

        $('#search-server-field').removeClass('is-hidden');
    }
}

function toggleRestriction(target) {
    let t = $(target);

    if (t.hasClass('ricon') && (t.hasClass('icon') || t.hasClass('fas'))) {
        toggleRestriction(target.parentNode);
        return;
    } else if (!t.hasClass('restriction-button'))
        return;

    if (t.hasClass('is-outlined')) {
        t.removeClass('is-outlined');

        if (t.attr('id') === 'search-restriction-warning')
            $('.restriction-button:not(#search-restriction-warning)').addClass('is-hidden').addClass('is-outlined');
        else
            $('#search-restriction-warning').addClass('is-hidden').addClass('is-outlined');
    } else {
        t.addClass('is-outlined');
        if (t.attr('id') === 'search-restriction-warning')
            $('.restriction-button:not(#search-restriction-warning)').removeClass('is-hidden');
        else if (!$('.restriction-button:not(.is-outlined):not(#search-restriction-warning)').length)
            $('#search-restriction-warning').removeClass('is-hidden');
    }
}

function clickedAdminCheck() {
    $('#search-admin-info').addClass('is-hidden');
    $('#search-admin-field').removeClass('is-hidden'); 
}

function handleSessionCheck() {
    if ($('#search-time-session-check').prop('checked')) {
        $('#search-time-game-timed-check').prop('checked', false);
        $('#search-time-permanent-check').prop('checked', false);
        $('#search-perm-check-field').addClass('is-hidden');
        $('#search-game-timed-check-field').addClass('is-hidden');
        $('#search-time-duration-field').addClass('is-hidden');
        $('#search-time-timeleft-field').addClass('is-hidden');
        $('#search-time-date-expiration-field').addClass('is-hidden');
    } else {
        $('#search-perm-check-field').removeClass('is-hidden');
        $('#search-game-timed-check-field').removeClass('is-hidden');
        $('#search-time-duration-field').removeClass('is-hidden');
        $('#search-time-timeleft-field').removeClass('is-hidden');
        $('#search-time-date-expiration-field').removeClass('is-hidden');
    }
}

function handlePermanentCheck() {
    if ($('#search-time-permanent-check').prop('checked')) {
        $('#search-time-session-check').prop('checked', false);
        $('#search-time-game-timed-check').prop('checked', false);
        $('#search-session-check-field').addClass('is-hidden');
        $('#search-game-timed-check-field').addClass('is-hidden');
        $('#search-time-duration-field').addClass('is-hidden');
        $('#search-time-timeleft-field').addClass('is-hidden');
        $('#search-time-date-expiration-field').addClass('is-hidden');
    } else {
        $('#search-session-check-field').removeClass('is-hidden');
        $('#search-game-timed-check-field').removeClass('is-hidden');
        $('#search-time-duration-field').removeClass('is-hidden');
        $('#search-time-timeleft-field').removeClass('is-hidden');
        $('#search-time-date-expiration-field').removeClass('is-hidden');
    }
}

function handleGameTimeCheck() {
    if ($('#search-time-game-timed-check').prop('checked')) {
        $('#search-time-session-check').prop('checked', false);
        $('#search-time-permanent-check').prop('checked', false);
        $('#search-session-check-field').addClass('is-hidden');
        $('#search-perm-check-field').addClass('is-hidden');
        $('#search-time-date-expiration-field').addClass('is-hidden');
    } else {
        $('#search-session-check-field').removeClass('is-hidden');
        $('#search-perm-check-field').removeClass('is-hidden');
        $('#search-time-date-expiration-field').removeClass('is-hidden');
    }
}

async function loadSearchModal() {
    resetSearchModal();

    closeModals();

    //Setup admins
    let admins_req = await gbRequest('GET', '/api/admin/', null);

    if (!admins_req.ok) {
        throw admins_req.error();
    }

    let admins = await admins_req.json()

    let adminSel = $('#search-admin-selector');

    adminSel.empty();

    adminSel.append($('<option>').attr('value', 0).text('<Any>').prop('selected', true));

    for (let i = 0; i < admins.length; i++) {
        if (admins[i]['permissions'] <= 0)
            continue;
        let el = $('<option>');
        if (admins[i]['admin_id'])
            el.attr('value', admins[i]['admin_id']);

        if (admins[i].hasOwnProperty('admin_name'))
            el.text(admins[i]['admin_name']);
        else
            el.text(admins[i]['admin_id']);

        adminSel.append(el);
    }


    //Setup servers
    let servers_req = await gbRequest('GET', '/api/server/', null);

    if (!servers_req.ok) {
        throw servers_req.error();
    }

    let servers = await servers_req.json()

    let serverSel = $('#search-scope-server-selector');

    serverSel.empty();

    serverSel.append($('<option>').attr('value', 0).text('<Any>').prop('selected', true));

    for (let i = 0; i < servers.length; i++) {
        if (!servers[i]['enabled'] || !servers[i]['id'])
            continue;
        let el = $('<option>');
        if (servers[i]['id'])
            el.attr('value', servers[i]['id']);

        if (servers[i].hasOwnProperty('friendly_name'))
            el.text(servers[i]['friendly_name']);
        else if (servers[i]['game_port'])
            el.text(`${servers[i]['ip']}:${servers[i]['game_port']}`);
        else
            el.text(servers[i]['ip']);

        serverSel.append(el);
    }

    //Setup and show the error modal
    $('#advanced-search-modal').addClass('is-active');
    $('#advanced-search-modal .modal-card-body').get(0).scrollTo(0,0);

    $('#htmlRoot').addClass('is-clipped');

    $('#search-loading-modal').removeClass('is-loading');

    $('.search-dismiss').off('click').click(function () {
        resetSearchModal();
        closeModals();
    });

    $('.search-dismiss-error').click(function () {
        $('#search-create-error').addClass('is-hidden');
    })

    $('#search-submit').click(beginSearch);
}

function openSearchModal() {
    let cl = $('#search-loading-modal');

    if (cl.hasClass('is-loading'))
        return;

    cl.addClass('is-loading');

    loadSearchModal().catch(logException);
}

function beginSearch() {
    //First request

    let createSearch = createSearchQuery();

    //Failure, the second index is the error
    if (!createSearch[0]) {
        $('#search-create-error-msg').text(createSearch[1]);
        $('#search-create-error').removeClass('is-hidden');
        return;
    }

    //Success, the second index is the request type and the third is the actual request struct

    window.location.href = '../infractions' + createSearch[1];
}

function createSearchQuery() {
    let query = '';

    // User
    if ($('#search-user-vpn-check').length && $('#search-user-vpn-check').prop('checked'))
        query = query.concat('&is_vpn=true');

    if ($('#search-user-name').val().trim().length > 0)
        query = query.concat(`&gs_name=${$('#search-user-name').val().trim()}`);
    
    if ($('#search-user-gsid').val().trim().length > 0) {
        query = query.concat(`&gs_id=${$('#search-user-gsid').val().trim()}`);
        query = query.concat(`&gs_service=${$('#search-user-service-selector').val()}`);
    }

    if ($('#search-user-ip').length && $('#search-user-ip').val().trim().length > 0)
        query = query.concat(`&ip=${$('#search-user-ip').val().trim()}`);

    // Admin
    if ($('#search-admin-system-check').prop('checked'))
        query = query.concat('&is_system=true');
    else if ($('#search-admin-demoted-check').prop('checked')) {
        if ($('#search-admin-name').val().trim().length > 0)
            query = query.concat(`&admin=${$('#search-admin-name').val()}`);

        if ($('#search-admin-id').val().trim().length > 0)
            query = query.concat(`&admin_id=${$('#search-admin-id').val()}`);
    }
    else if ($('#search-admin-admin-check').prop('checked')) {
        if ($('#search-admin-selector').val().length > 1)
            query = query.concat(`&admin_id=${$('#search-admin-selector').val()}`);
    }

    // Scope
    if ($('#search-scope-web-check').prop('checked'))
        query = query.concat('&is_web=true');
    else if ($('#search-scope-server-selector').val().length > 1)
        query = query.concat(`&server=${$('#search-scope-server-selector').val()}`);

    if ($('#search-scope-global-check').prop('checked'))
        query = query.concat('&is_global=true');
    else if ($('#search-scope-community-check').prop('checked'))
        query = query.concat('&is_super_global=true');
    else if ($('#search-scope-server-check').prop('checked'))
        query = query.concat('&is_server=true');

    // Reason
    if ($('#search-reason-creation').val().trim().length > 0)
        query = query.concat(`&reason=${$('#search-reason-creation').val().trim()}`);

    if ($('#search-reason-removal').val().trim().length > 0)
        query = query.concat(`&ureason=${$('#search-reason-removal').val().trim()}`);

    // Restriction
    if (!$('#search-restriction-warning').hasClass('is-outlined'))
        query = query.concat('&is_warning=true');
    else {
        if (!$('#search-restriction-voice').hasClass('is-outlined'))
            query = query.concat('&is_voice=true');

        if (!$('#search-restriction-text').hasClass('is-outlined'))
            query = query.concat('&is_text=true');

        if (!$('#search-restriction-join').hasClass('is-outlined'))
            query = query.concat('&is_ban=true');

        if (!$('#search-restriction-admin-chat').hasClass('is-outlined'))
            query = query.concat('&is_admin_chat=true');

        if (!$('#search-restriction-call-admin').hasClass('is-outlined'))
            query = query.concat('&is_call_admin=true');
    }
    
    // Time
    if ($('#search-time-session-check').prop('checked')) 
        query = query.concat('&is_session=true');
    else if ($('#search-time-permanent-check').prop('checked'))
        query = query.concat('&is_permanent=true');
    else if ($('#search-time-game-timed-check').prop('checked'))
        query = query.concat('&is_decl_online_only=true');

    if (!$('#search-time-duration-field').hasClass('is-hidden') && $('#search-time-duration-entry').val().trim().length > 0) {
        let n = parseInt($('#search-time-duration-unit-selector').val())

        if (Number.isNaN(n))
            return [false, 'Total Time must be a number']

        query = query.concat(`&duration=${n * timeMultipliers[$('#search-time-duration-unit-selector').val()]}`);
        query = query.concat(`&duration_comparison_mode=${$('#search-time-duration-compare-selector').val()}`);
    }

    if (!$('#search-time-timeleft-field').hasClass('is-hidden') && $('#search-time-timeleft-entry').val().trim().length > 0) {
        let n = parseInt($('#search-time-timeleft-unit-selector').val())

        if (Number.isNaN(n))
            return [false, 'Time Left must be a number']

        query = query.concat(`&time_left=${n * timeMultipliers[$('#search-time-timeleft-unit-selector').val()]}`);
        query = query.concat(`&time_left_comparison_mode=${$('#search-time-timeleft-compare-selector').val()}`);
    }

    if (!$('#search-time-date-creation-field').hasClass('is-hidden') && $('#search-time-date-creation').val().length > 0) {
        query = query.concat(`&created=${Date.parse($('#search-time-date-creation').val())/1000}`);
        query = query.concat(`&created_comparison_mode=${$('#search-time-date-creation-compare-selector').val()}`);
    }

    if (!$('#search-time-date-expiration-field').hasClass('is-hidden') && $('#search-time-date-expiration').val().length > 0) {
        query = query.concat(`&expires=${Date.parse($('#search-time-date-expiration').val())/1000}`);
        query = query.concat(`&expires_comparison_mode=${$('#search-time-date-expiration-compare-selector').val()}`);
    }

    // Status
    if ($('#search-status-removed-check').prop('checked'))
        query = query.concat('&is_removed=true');
    else if ($('#search-status-expired-check').prop('checked'))
        query = query.concat('&is_expired=true');
    else if ($('#search-status-active-check').prop('checked'))
        query = query.concat('&is_active=true');


    if (query.length == 0)
        return [false, 'You must give at least 1 search parameter']
    else
        return [true, '?' + query.trim().substring(1)];
}

const timeMultipliers = {
    'm': 60,
    'h': 3600,
    'd': 3600 * 24,
    'w': 3600 * 24 * 7,
    'mo': 3600 * 24 * 30,
    'y': 3600 * 24 * 365
}