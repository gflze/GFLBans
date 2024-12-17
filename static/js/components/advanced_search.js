let loadedAdvancedSearch = false;

$(document).ready(function () {
    $('#advancedSearchToggle').click(openSearchModal);
});

function openSearchModal() {
    const cl = $('#search-loading-modal');

    if (cl.hasClass('is-loading'))
        return;

    cl.addClass('is-loading');

    loadSearchModal().catch(logException);

    cl.removeClass('is-loading');
}

async function loadSearchModal() {
    closeModals();

    if (!loadedAdvancedSearch) {
        $('#search-scope-web-check').click(handleWebCheck);
        $('[name="time-type"]').click(handleTimeCheck);
        $('[name="status-type"]').click(handleStatusCheck);
        $('#search-admin-admin-check').click(clickedAdminCheck);
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
        $('#search-submit').click(beginSearch);
        $('#advanced-search-modal .input').on('keypress', function(event) {
            if (event.which === 13)
                document.getElementById('search-submit').click();
        });

        resetSearchModal();

        //Setup admins
        const admins_req = await gbRequest('GET', '/api/admin/', null);

        if (!admins_req.ok) {
            throw admins_req.error();
        }

        const admins = await admins_req.json();

        const adminSel = $('#search-admin-selector');

        adminSel.empty();

        adminSel.append($('<option>').attr('value', 0).text('<Any>').prop('selected', true));

        for (let i = 0; i < admins.length; i++) {
            if (admins[i]['permissions'] <= 0)
                continue;
            const el = $('<option>');
            if (admins[i]['admin_id'])
                el.attr('value', admins[i]['admin_id']);

            if (admins[i].hasOwnProperty('admin_name'))
                el.text(admins[i]['admin_name']);
            else
                el.text(admins[i]['admin_id']);

            adminSel.append(el);
        }

        //Setup servers
        const servers_req = await gbRequest('GET', '/api/server/', null);

        if (!servers_req.ok) {
            throw servers_req.error();
        }

        const servers = await servers_req.json();

        const serverSel = $('#search-scope-server-selector');

        serverSel.empty();

        serverSel.append($('<option>').attr('value', 0).text('<Any>').prop('selected', true));

        for (let i = 0; i < servers.length; i++) {
            if (!servers[i]['enabled'] || !servers[i]['id'])
                continue;
            const el = $('<option>');
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

        loadUrlParams();
        loadedAdvancedSearch = true;
    }

    $('#advanced-search-modal').addClass('is-active');
    $('#advanced-search-modal .modal-card-body').get(0).scrollTo(0,0);

    $('#htmlRoot').addClass('is-clipped');

    $('.search-dismiss').off('click').click(function () {
        closeModals();
    });

    $('.search-dismiss-error').click(function () {
        $('#search-create-error').addClass('is-hidden');
    });
}

function resetSearchModal() {
    // User
    $('#search-user-vpn-check').prop('checked', false);
    $('#search-user-name').val('');
    $('#search-user-gsid').val('');
    $('#search-user-service-selector').val('steam');
    $('#search-user-ip').val('');

    // Admin
    $('#search-admin-admin-check').trigger('click');
    $('#search-admin-name').val('');
    $('#search-admin-name').removeClass('is-hidden');
    $('#search-admin-id').val('');
    $('#search-admin-id').removeClass('is-hidden');

    // Scope
    $('#search-scope-web-check').prop('checked', true).trigger('click');
    $('#search-scope-server-check').prop('disabled', false);
    $('#search-scope-server-label').removeClass('is-hidden');
    $('#search-scope-any-check').trigger('click');

    // Reasons
    $('#search-reason-creation').val('');
    $('#search-reason-removal').val('');

    // Restriction Types
    $('#search-restriction-warning').addClass('is-outlined');
    $('.restriction-button').addClass('is-outlined');

    // Status
    $('#search-status-any-check').trigger('click');

    // Time/Duration
    $('#search-time-any-check').trigger('click');
    $('#search-time-duration-compare-selector').val('eq');
    $('#search-time-duration-entry').val('');
    $('#search-time-duration-unit-selector').val('h');
    $('#search-time-timeleft-compare-selector').val('eq');
    $('#search-time-timeleft-entry').val('');
    $('#search-time-timeleft-unit-selector').val('h');
    $('#search-time-duration-field').removeClass('is-hidden');

    $('#search-time-date-creation').val('');
    $('#search-time-date-expiration').val('');
    $('#search-time-date-creation-compare-selector').val('eq');
    $('#search-time-date-expiration-compare-selector').val('eq');
}

function loadUrlParams() {
    const getParams = new URLSearchParams(window.location.search);

    // Quick search
    if (urlParams.has('search'))
        $('#navbarContents [action="/infractions"] input').val(urlParams.get('search'));

    // User
    if ($('#search-user-vpn-check').length && urlParams.has('is_vpn'))
        $('#search-user-vpn-check').trigger('click');
    if (urlParams.has('gs_name'))
        $('#search-user-name').val(urlParams.get('gs_name'));
    if (urlParams.has('gs_id'))
        $('#search-user-gsid').val(urlParams.get('gs_id'));
    if (urlParams.has('gs_service'))
        $('#search-user-service-selector').val(urlParams.get('gs_service')).trigger('click');
    if ($('#search-user-ip').length && urlParams.has('ip'))
        $('#search-user-ip').val(urlParams.get('ip'));

    // Admin
    if (urlParams.has('is_system'))
        $('#search-admin-system-check').trigger('click');
    else {
        if (urlParams.has('admin_id')) {
            if($(`#search-admin-selector [value="${urlParams.get('admin_id')}"]`).length) {
                $('#search-admin-admin-check').trigger('click');
                $('#search-admin-selector').val(urlParams.get('admin_id'));
            } else {
                $('#search-admin-demoted-check').trigger('click');
                $('#search-admin-id').val(urlParams.get('admin_id')).trigger('input');
            }
        }
        if (urlParams.has('admin')) {
            $('#search-admin-demoted-check').trigger('click');
            $('#search-admin-name').val(urlParams.get('admin')).trigger('input');
        }
    }

    // Scope
    if (urlParams.has('is_web'))
        $('#search-scope-web-check').trigger('click');
    else if (urlParams.has('server'))
        $('#search-scope-server-selector').val(urlParams.get('server'));

    if (urlParams.has('is_global') && urlParams.get('is_global') === 'false'
        && urlParams.has('is_super_global') && urlParams.get('is_super_global') === 'false')
        $('#search-scope-server-check').trigger('click');
    else if (urlParams.has('is_global'))
        $('#search-scope-global-check').trigger('click');
    else if (urlParams.has('is_super_global'))
        $('#search-scope-community-check').trigger('click');

    // Reasons
    if (urlParams.has('reason'))
        $('#search-reason-creation').val(urlParams.get('reason'));
    if (urlParams.has('ureason'))
        $('#search-reason-removal').val(urlParams.get('ureason'));

    // Restriction Types
    if (urlParams.has('is_voice') && urlParams.get('is_voice') === 'false'
        && urlParams.has('is_text') && urlParams.get('is_text') === 'false'
        && urlParams.has('is_ban') && urlParams.get('is_ban') === 'false'
        && urlParams.has('is_admin_chat') && urlParams.get('is_admin_chat') === 'false'
        && urlParams.has('is_call_admin') && urlParams.get('is_call_admin') === 'false'
        && urlParams.has('is_item') && urlParams.get('is_item') === 'false') {
        $('#search-restriction-warning').trigger('click');
    } else {
        if (urlParams.has('is_voice'))
            $('#search-restriction-voice').trigger('click');
        if (urlParams.has('is_text'))
            $('#search-restriction-text').trigger('click');
        if (urlParams.has('is_ban'))
            $('#search-restriction-join').trigger('click');
        if (urlParams.has('is_admin_chat'))
            $('#search-restriction-admin-chat').trigger('click');
        if (urlParams.has('is_call_admin'))
            $('#search-restriction-call-admin').trigger('click');
        if (urlParams.has('is_item'))
            $('#search-restriction-item').trigger('click');
    }

    // Status
    if (urlParams.has('is_expired'))
        $('#search-status-expired-check').trigger('click');
    else if (urlParams.has('is_active'))
        $('#search-status-active-check').trigger('click');
    else if (urlParams.has('is_removed'))
        $('#search-status-removed-check').trigger('click');

    // Time/Duration
    if (urlParams.has('is_permanent'))
        $('#search-time-permanent-check').trigger('click');
    else if (urlParams.has('is_session'))
        $('#search-time-session-check').trigger('click');
    else if (urlParams.has('is_decl_online_only') && urlParams.get('is_decl_online_only') === 'false')
        $('#search-time-real-world-timed-check').trigger('click');
    else if (urlParams.has('is_decl_online_only'))
        $('#search-time-game-timed-check').trigger('click');
    if (urlParams.has('created')) {
        const timestamp = parseInt(getParams.get('created'), 10) * 1000;
        const date = new Date(timestamp);
        const formattedDate = date.toISOString().split('T')[0];
        $('#search-time-date-creation').val(formattedDate);
    }
    if (urlParams.has('created_comparison_mode'))
        $('#search-time-date-creation-compare-selector').val(urlParams.get('created_comparison_mode'));
    if (urlParams.has('expires')) {
        const timestamp = parseInt(getParams.get('expires'), 10) * 1000;
        const date = new Date(timestamp);
        const formattedDate = date.toISOString().split('T')[0];
        $('#search-time-date-expiration').val(formattedDate);
    }
    if (urlParams.has('expires_comparison_mode'))
        $('#search-time-date-expiration-compare-selector').val(urlParams.get('expires_comparison_mode'));
    if (urlParams.has('time_left')) {
        $('#search-time-timeleft-entry').val(urlParams.get('time_left')/60);
        $('#search-time-timeleft-unit-selector').val('m');
    }
    if (urlParams.has('time_left_comparison_mode'))
        $('#search-time-timeleft-compare-selector').val(urlParams.get('time_left_comparison_mode'));
    if (urlParams.has('duration')) {
        $('#search-time-duration-entry').val(urlParams.get('duration')/60);
        $('#search-time-duration-unit-selector').val('m');
    }
    if (urlParams.has('duration_comparison_mode'))
        $('#search-time-duration-compare-selector').val(urlParams.get('duration_comparison_mode'));
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
    const t = $(target);

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

function handleTimeCheck() {
    $('#search-time-duration-field').removeClass('is-hidden');
    $('#search-time-timeleft-field').addClass('is-hidden');
    $('#search-time-date-expiration-field').addClass('is-hidden');
    $('#search-time-date-expiration-field').addClass('is-hidden');

    if ($('#search-time-session-check').prop('checked') || $('#search-time-permanent-check').prop('checked'))
        $('#search-time-duration-field').addClass('is-hidden');
    else if ($('#search-time-game-timed-check').prop('checked'))
        $('#search-time-timeleft-field').removeClass('is-hidden');
    else if ($('#search-time-real-world-timed-check').prop('checked'))
        $('#search-time-date-expiration-field').removeClass('is-hidden');
}

function handleStatusCheck() {
    $('#search-time-permanent-label').removeClass('is-hidden');
    $('#search-time-session-label').removeClass('is-hidden');

    if ($('#search-status-active-check').prop('checked')) {
        if ($('#search-time-session-check').prop('checked')) {
            $('#search-time-session-check').prop('checked', false);
            $('#search-time-any-check').prop('checked', true);
        }
        $('#search-time-session-label').addClass('is-hidden');
        $('#search-reason-removal').addClass('is-hidden');
    } else if ($('#search-status-expired-check').prop('checked')) {
        if ($('#search-time-permanent-check').prop('checked')) {
            $('#search-time-permanent-check').prop('checked', false);
            $('#search-time-any-check').prop('checked', true);
        }
        $('#search-time-permanent-label').addClass('is-hidden');
        $('#search-reason-removal').addClass('is-hidden');
    } else
        $('#search-reason-removal').removeClass('is-hidden');
    handleTimeCheck();
}

function beginSearch() {
    const createSearch = createSearchQuery();

    // Failure, the second index is the error
    if (!createSearch[0]) {
        $('#search-create-error-msg').text(createSearch[1]);
        $('#search-create-error').removeClass('is-hidden');
        $('#advanced-search-modal .modal-card-body').get(0).scrollTo(0,0);
        return;
    }

    // Success, the second index contains the GET parameters
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
    } else if ($('#search-admin-admin-check').prop('checked')) {
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
        query = query.concat('&is_global=false&is_super_global=false');

    // Reason
    if ($('#search-reason-creation').val().trim().length > 0)
        query = query.concat(`&reason=${$('#search-reason-creation').val().trim()}`);

    if (!$('#search-reason-removal').hasClass('is-hidden') && $('#search-reason-removal').val().trim().length > 0)
        query = query.concat(`&ureason=${$('#search-reason-removal').val().trim()}`);

    // Restriction
    if (!$('#search-restriction-warning').hasClass('is-outlined'))
        query = query.concat(
            '&is_voice=false'
            + '&is_text=false'
            + '&is_ban=false&'
            + 'is_admin_chat=false&'
            + 'is_call_admin=false'
            + '&is_item=false'
        );
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

        if (!$('#search-restriction-item').hasClass('is-outlined'))
            query = query.concat('&is_item=true');
    }

    // Time
    if ($('#search-time-session-check').prop('checked'))
        query = query.concat('&is_session=true');
    else if ($('#search-time-permanent-check').prop('checked'))
        query = query.concat('&is_permanent=true');
    else if ($('#search-time-game-timed-check').prop('checked'))
        query = query.concat('&is_decl_online_only=true');
    else if ($('#search-time-real-world-timed-check').prop('checked'))
        query = query.concat('&is_decl_online_only=false');

    if (
        !$('#search-time-date-creation-field').hasClass('is-hidden')
        && $('#search-time-date-creation').val().length > 0
        && !$('#search-time-date-expiration-field').hasClass('is-hidden')
        && $('#search-time-date-expiration').val().length > 0
        && $('#search-time-date-creation').val() >= $('#search-time-date-expiration').val()
    ) {
        return [false, 'Expiration Date must be after Creation Date'];
    }

    if (
        !$('#search-time-date-creation-field').hasClass('is-hidden')
        && $('#search-time-date-creation').val().length > 0
    ) {
        const dateParts = $('#search-time-date-creation').val().split('-');
        const localDate = (
            new Date(
                parseInt(dateParts[0], 10),
                parseInt(dateParts[1], 10) - 1,
                parseInt(dateParts[2], 10)
            )
        );
        query = query.concat(`&created=${localDate.getTime()/1000}`);
        query = query.concat(`&created_comparison_mode=${$('#search-time-date-creation-compare-selector').val()}`);
    }

    if (
        !$('#search-time-date-expiration-field').hasClass('is-hidden')
        && $('#search-time-date-expiration').val().length > 0
    ) {
        const dateParts = $('#search-time-date-expiration').val().split('-');
        const localDate = new Date(
            parseInt(dateParts[0], 10),
            parseInt(dateParts[1], 10) - 1,
            parseInt(dateParts[2], 10)
        );
        query = query.concat(`&expires=${localDate.getTime()/1000}`);
        query = query.concat(`&expires_comparison_mode=${$('#search-time-date-expiration-compare-selector').val()}`);
    }

    if (
        !$('#search-time-duration-field').hasClass('is-hidden')
        && $('#search-time-duration-entry').val().trim().length > 0
    ) {
        const n = parseInt($('#search-time-duration-entry').val());

        if (Number.isNaN(n))
            return [false, 'Total Time must be a number'];
        else if (n <= 0)
            return [false, 'Total Time must be greater than zero'];

        query = query.concat(`&duration=${n * timeMultipliers[$('#search-time-duration-unit-selector').val()]}`);
        query = query.concat(`&duration_comparison_mode=${$('#search-time-duration-compare-selector').val()}`);
    }

    if (
        !$('#search-time-timeleft-field').hasClass('is-hidden')
        && $('#search-time-timeleft-entry').val().trim().length > 0
    ) {
        const n = parseInt($('#search-time-timeleft-entry').val());

        if (Number.isNaN(n))
            return [false, 'Time Left must be a number'];
        else if (n <= 0)
            return [false, 'Time Left must be greater than zero'];

        const dur = parseInt($('#search-time-duration-entry').val());

        if (
            !Number.isNaN(dur)
            && n * timeMultipliers[$('#search-time-timeleft-unit-selector').val()]
                > dur * timeMultipliers[$('#search-time-duration-unit-selector').val()]
        )
            return [false, 'Time Left cannot be greater than Total Time'];

        query = query.concat(`&time_left=${n * timeMultipliers[$('#search-time-timeleft-unit-selector').val()]}`);
        query = query.concat(`&time_left_comparison_mode=${$('#search-time-timeleft-compare-selector').val()}`);
    }

    // Status
    if ($('#search-status-removed-check').prop('checked'))
        query = query.concat('&is_removed=true');
    else if ($('#search-status-expired-check').prop('checked'))
        query = query.concat('&is_expired=true');
    else if ($('#search-status-active-check').prop('checked'))
        query = query.concat('&is_active=true');


    if (query.length == 0)
        return [false, 'You must give at least 1 search parameter'];
    else
        return [true, '?' + query.trim().substring(1)];
}

const timeMultipliers = {
    'm':  60,
    'h':  3600,
    'd':  3600 * 24,
    'w':  3600 * 24 * 7,
    'mo': 3600 * 24 * 30,
    'y':  3600 * 24 * 365
};
