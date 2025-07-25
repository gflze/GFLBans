// User specification
const cUserId = document.getElementById('gameIdEntry');
const cIpEntry = document.getElementById('ipEntry');
// Scoping
const cWebCheck = document.getElementById('isWebToggle');
const cTargetServer = document.getElementById('serverSelector');
const cServerRadio = document.getElementById('serverOnlyCheck');
const cServerLabel = document.getElementById('serverOnlyLabel');
const cTargetServerField = document.getElementById('targetServerField');
const cGlobalRadio = document.getElementById('globalCheck');
const cGlobalLabel = document.getElementById('globalLabel');
// Reason / evidence
const cReasonEntry = document.getElementById('reasonEntry');
const cFileInput = document.getElementById('fileInput');
const cFileName = document.getElementById('fileName');
// Restrictions
const cRestrictionSection = document.getElementById('cRestrictionsSection');
const cVoiceBtn = document.getElementById('restrictVoice');
const cBanBtn = document.getElementById('restrictJoin');
const cTextBtn = document.getElementById('restrictText');
const cAdminChatBtn = document.getElementById('restrictAdminChat');
const cCallAdminBtn = document.getElementById('restrictCallAdmin');
const cItemBtn = document.getElementById('restrictItem');
// Expiration
const cExpirationSection = document.getElementById('cExpirationSection');
const cPermanentCheck = document.getElementById('permanentCheck');
const cTimeDecCheck = document.getElementById('timeDecCheck');
const cDurationEntry = document.getElementById('durationEntry');
const cDurationUnit = document.getElementById('unitSelector');
const cTimeDecCheckField = document.getElementById('cTimeDecCheckField');
const cDurationField = document.getElementById('cDurationField');
const cPermCheckField = document.getElementById('cPermCheckField');

// Loading modal
const cLoadingModal = document.getElementById('cLoadingModal');

// Utility functions
function setSelection(selector, selection) {
    for (let i = 0; i < selector.children.length; i++) {
        if (selector.children[i].hasAttribute('value') && selector.children[i].getAttribute('value') === selection) {
            selector.selectedIndex = i;
        }
    }
}

function resetModal() {
    // Default user info
    $(cUserId).val('');
    $(cIpEntry).val('');

    // By default, we do not make web infractions, so we should show the target server box and enable the 'server' tick
    $(cWebCheck).prop('checked', false);
    $(cServerRadio).prop('disabled', false);
    cServerLabel.removeAttribute('disabled');
    $(cTargetServerField).removeClass('is-hidden');

    $('.scope-check').prop('checked', false);

    // If we have permission for global, default to it. Otherwise hide and disable
    const gp = $(cGlobalRadio).attr('data-has-permissions') !== '1';
    $(cGlobalRadio).prop('disabled', gp);
    if (gp) {
        cGlobalLabel.setAttribute('disabled', '1');
        $(cGlobalLabel).addClass('is-hidden');
        $(serverOnlyCheck).prop('checked', true);
    } else {
        cGlobalLabel.removeAttribute('disabled');
        $(cGlobalLabel).removeClass('is-hidden');
        $(cGlobalRadio).prop('checked', true);
    }

    $(cRestrictionSection).removeClass('is-hidden');
    $(cExpirationSection).removeClass('is-hidden');

    // Clear evidence / reasoning text boxes
    $(cReasonEntry).val('');
    cFileInput.value = '';
    $(cFileName).text('No file uploaded.');

    $('.rbtn').addClass('is-outlined');

    $(cTimeDecCheckField).removeClass('is-hidden');
    $(cDurationField).removeClass('is-hidden');

    $(cPermanentCheck).prop('checked', false);
    $(cTimeDecCheck).prop('checked', false);
    $(cDurationEntry).val('');
    setSelection(cDurationUnit, 'h');
    $('#cInfractionSubmit').off('click');

}

function handleWebCheckChanged() {
    if ($(cWebCheck).prop('checked')) {
        $(cServerRadio).prop('disabled', true);
        cServerLabel.setAttribute('disabled', '1');

        $(cTargetServerField).addClass('is-hidden');

        if ($(cServerRadio).prop('checked')) {
            $(cServerRadio).prop('checked', false);

            if ($(cGlobalRadio).attr('data-has-permissions') === '1')
                $(cGlobalRadio).prop('checked', true);
        }
    } else {
        $(cServerRadio).prop('disabled', false);
        cServerLabel.removeAttribute('disabled');
        $(cTargetServerField).removeClass('is-hidden');
    }
}

function toggleButton(target) {
    const t = $(target);

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

function handlePermCheck() {
    if ($(cPermanentCheck).prop('checked')) {
        $(cTimeDecCheck).prop('checked', false);
        handleTimeDecCheck();
        $(cTimeDecCheckField).addClass('is-hidden');
        $(cDurationField).addClass('is-hidden');
    } else {
        $(cDurationField).removeClass('is-hidden');
        $(cTimeDecCheckField).removeClass('is-hidden');
    }
}

function handleTimeDecCheck() {
    if ($(cTimeDecCheck).prop('checked')) {
        $(cPermanentCheck).prop('checked', false);
        handlePermCheck();
        $(cPermCheckField).addClass('is-hidden');
    } else {
        $(cPermCheckField).removeClass('is-hidden');
    }
}

async function loadModal() {
    resetModal();

    closeModals();

    // Setup servers
    const servers_req = await gbRequest('GET', '/api/server/', null);

    if (!servers_req.ok) {
        throw servers_req.error();
    }

    const servers = await servers_req.json();

    servers.sort(function(a, b) {
        let aName = a['ip'];
        if (a.hasOwnProperty('group_name'))
            aName = a['group_name'].toLowerCase();
        else if (a.hasOwnProperty('game_port'))
            aName = `${a['ip']}:${a['game_port']}`;

        let bName = b['ip'];
        if (b.hasOwnProperty('group_name'))
            bName = b['group_name'].toLowerCase();
        else if (b.hasOwnProperty('game_port'))
            bName = `${b['ip']}:${b['game_port']}`;

        return ((aName < bName) ? -1 : ((aName > bName) ? 1 : 0));
    });

    const serverSel = $('#serverSelector');
    serverSel.empty();

    for (let i = 0; i < servers.length; i++) {
        if (!servers[i]['enabled'])
            continue;
        const el = document.createElement('option');
        el.setAttribute('value', servers[i]['id']);

        if (servers[i].hasOwnProperty('friendly_name')) {
            el.innerText = servers[i]['friendly_name'];
        } else {
            el.innerText = servers[i]['ip'];
        }

        if (i === 0)
            $(el).prop('selected', true);

        serverSel.append(el);
    }

    // Setup and show the error modal
    $('#createModal').addClass('is-active');
    $('#createModal .modal-card-body').get(0).scrollTo(0,0);

    $('#htmlRoot').addClass('is-clipped');

    $('#createInfractionLoader').removeClass('is-loading');

    $('.cInfractionDismiss').off('click').click(function () {
        resetModal();
        closeModals();
    });

    $('.cDismissError').click(function () {
        $('#infractionCreateError').addClass('is-hidden');
    });

    $('#cInfractionSubmit').click(submitInfraction);
}

function openModal() {

    const cl = $('#createInfractionLoader');

    if (cl.hasClass('is-loading')) {
        return;
    }

    cl.addClass('is-loading');

    loadModal().catch(logException);
}

$(document).ready(function () {
    $(cWebCheck).click(handleWebCheckChanged);
    $(cPermanentCheck).click(handlePermCheck);
    $(cTimeDecCheck).click(handleTimeDecCheck);
    $('.rbtn').click(function (ev) {
        toggleButton(ev.target);
    });

    $(cFileInput).change(function () {
        const fn = $(cFileInput)[0].files[0].name;
        $(cFileName).text(fn);
    });

    $('#createInfractionLoader').click(openModal);
});

function submitInfraction() {
    setLoading();

    // First request

    const createCall = createAndValidateInfraction();

    // Failure, the second index is the error
    if (!createCall[0]) {
        $('#infractionCreateErrorMsg').text(createCall[1]);
        $('#infractionCreateError').removeClass('is-hidden');
        $('#loadingModal').removeClass('is-active');
        $('#createModal .modal-card-body').get(0).scrollTo(0,0);
        return;
    }

    // Success, the second index is the request type and the third is the actual request struct

    let route = '/api/infractions/';

    gbRequest('POST', route, createCall[2], true).then(handleInfractionSubmission).catch(logException);
}

function handleInfractionSubmission(resp) {
    if (!resp.ok) {
        console.log(resp);
        resp.text().then(function (t) {
            console.log(t);
        });
        throw 'Server returned a non-OK error code.';
    }

    if ($(cFileInput).val() !== '') {
        resp.json().then(function (j) {
            uploadAttachment(j['id'], cFileInput.files[0].name, cFileInput.files[0]).then(function () {
                closeModals();
                window.location.reload();
            });
        }).catch(function (e) {
            throw e;
        });

        return;
    }

    closeModals();

    window.location.reload();

}

function createAndValidateInfraction() {
    const infraction = {
        'player': {},
        'do_full_infraction': true
    };

    // Common
    if ($(cUserId).val().trim() !== '') {
        infraction['player']['gs_service'] = 'steam';
        infraction['player']['gs_id'] = $(cUserId).val().trim();
    }

    if ($(cIpEntry).val().trim() !== '') {
        infraction['player']['ip'] = $(cIpEntry).val().trim();
    }

    if (!infraction['player'].hasOwnProperty('gs_id') && !infraction['player'].hasOwnProperty('ip')) {
        return [false, 'You must target either an IP address, a player, or both!'];
    }

    // Assign server
    if (!$(cWebCheck).prop('checked')) {
        infraction['server'] = $(cTargetServer).val();
        infraction['scope'] = 'server';
    }

    // Scope
    if (
        ($(cWebCheck).prop('checked')
            || $(cGlobalRadio).prop('checked'))
        && $(cGlobalRadio).attr('data-has-permissions') === '1'
    )
        infraction['scope'] = 'global';

    // Reason
    if ($(cReasonEntry).val().trim() === '') {
        return [false, 'You must enter a reason!'];
    }

    infraction['reason'] = $(cReasonEntry).val().trim();

    // Check the file size
    // if ($(cFileInput).val() !== '' && cFileName.files[0].size > (30 * 1024 * 1024)) {
    //    return [false, 'The file must be no more than 30 MB.']
    // }

    // Allow STEAMID in the request field
    infraction['allow_normalize'] = true;

    // Restrictions. Only apply if button exists (length is non-zero) and pressed
    infraction['punishments'] = [];

    if ($(cVoiceBtn).length && !$(cVoiceBtn).hasClass('is-outlined')) {
        infraction['punishments'].push('voice_block');
    }

    if ($(cBanBtn).length && !$(cBanBtn).hasClass('is-outlined')) {
        if ($(cTimeDecCheck).prop('checked'))
            return [false, 'A ban cannot be playtime based.'];

        infraction['punishments'].push('ban');
    }

    if ($(cTextBtn).length && !$(cTextBtn).hasClass('is-outlined')) {
        infraction['punishments'].push('chat_block');
    }

    if ($(cCallAdminBtn).length && !$(cCallAdminBtn).hasClass('is-outlined')) {
        infraction['punishments'].push('call_admin_block');
    }

    if ($(cAdminChatBtn).length && !$(cAdminChatBtn).hasClass('is-outlined')) {
        infraction['punishments'].push('admin_chat_block');
    }

    if ($(cItemBtn).length && !$(cItemBtn).hasClass('is-outlined')) {
        infraction['punishments'].push('item_block');
    }

    // Duration
    try {
        if ($(cPermanentCheck).prop('checked')) {
            // A permanent infraction has no duration field
        } else if ($(cTimeDecCheck).prop('checked')) {
            infraction['playtime_based'] = true;
            infraction['duration'] = getInfractionSeconds();
        } else {
            infraction['playtime_based'] = false;
            infraction['duration'] = getInfractionSeconds();
        }
    } catch (e) {
        return [false, e];
    }

    return [true, false, infraction];
}

const multipliers = {
    'm': 60,
    'h': 3600,
    'd': 3600 * 24,
    'w': 3600 * 24 * 7,
    'mo': 3600 * 24 * 30,
    'y': 3600 * 24 * 365
};

function getInfractionSeconds() {
    const n = parseInt($(cDurationEntry).val());

    if (Number.isNaN((n))) {
        throw 'Duration must be a number!';
    }

    return n * multipliers[$(cDurationUnit).val()];
}

function setLoadingModal() {
    closeModals();

    $(cLoadingModal).addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');
}
