const viewModal = $('#infraction_view_modal');
const userAvatar = $('#avatar_img');
const userName = $('#user_name');
const createdAt = $('#createdAt');

const vpnTag = $('#fvpn');
const removedTag = $('#fremoved');
const expiredTag = $('#fexpired');
const systemTag = $('#fsystem');
const webTag = $('#fweb');

const idContainer = $('#idContainer');
const idLabel = $('#idLabel');
const idValue = $('#idValue');

const ipContainer = $('#ipContainer');
const ipLabel = $('#ipLabel')
const ipValue = $('#ipValue');

const timeValue = $('#timeValue');

const adminContainer = $('#adminContainer');
const issuedValue = $('#issuedValue');

const serverContainer = $('#serverContainer');
const serverValue = $('#serverValue')

const scopeValue = $('#scopeValue');

const reasonValue = $('#reasonValue')

const callAdminFlag = $('#callAdminFlag');
const adminChatFlag = $('#adminChatFlag');
const textChatFlag = $('#textChatFlag');
const voiceChatFlag = $('#voiceChatFlag');
const warningFlag = $('#warningFlag');
const banFlag = $('#banFlag');

const removedC = $('.rmEl');
const rOn = $('#removedOnValue');
const rBy = $('#removedByValue');
const rR = $('#removedReasonValue');

const commentContainer = $('#iComments');

const iOptions = $('#infOptions')

const ALL_P_FLAGS = 3968

let callAdminFlagEdit = $('#callAdminFlagEdit')
let adminChatFlagEdit = $('#adminChatFlagEdit')
let textChatFlagEdit = $('#textChatFlagEdit')
let voiceChatFlagEdit = $('#voiceChatFlagEdit')
let banFlagEdit = $('#banFlagEdit')
let restrictionsEditCell = $('#restrictionsEditCell')
let restrictionsEdit = $('#restrictionsEdit')
let restrictionsCancel = $('#restrictionsCancel')

let server_data = []

function resetViewModal() {
    $('.ptag').addClass('is-hidden');
    $('.ftag').addClass('is-hidden');

    idContainer.removeClass('is-hidden');
    ipContainer.removeClass('is-hidden');
    adminContainer.removeClass('is-hidden');
    serverContainer.removeClass('is-hidden');
    removedC.addClass('is-hidden')
    $('.edit').addClass('is-hidden');
    commentContainer.empty();
    $('#privateCheck').prop('checked', false);
    commentContainer.addClass('is-hidden');
    $('#commentState').removeClass('fa-sort-down').addClass('fa-sort-up');
    $('#commentCount').text('0');
    $('#commentText').prop('disabled', false).val('');
    $('#doPost').removeClass('is-loading').prop('disabled', true);
    $("#FileButton").removeClass("is-loading");
    $("#doFileUpload").prop("disabled", false);
    iOptions.addClass('is-hidden');
    $('.edit-cell').addClass('is-hidden');
    $('.data-cell').removeClass('is-hidden');
    $('#idValue').empty();
    restrictionsCancel.addClass('is-hidden');
    $('#cancelRemoval').removeAttr('disabled');
    $('#removeButton').removeAttr('disabled').removeClass('is-loading');
    $('#removalReason').val('');
}

async function setupViewModal(infraction) {
    let gbServers = await gbRequest('GET', '/api/server/?enabled_only=true');

    if (!gbServers.ok) {
        throw 'NOT OK'
    }

    server_data = await gbServers.json();


    viewModal.attr('data-infraction', infraction['id']);

    //Avatar
    if (infraction['player'].hasOwnProperty('gs_avatar')) {
        userAvatar.attr('src', '/file/uploads/' + infraction['player']['gs_avatar']['file_id'] + '/avatar.webp');
    } else {
        userAvatar.attr('src', '/static/fallback_av.png')
    }

    //Name
    if (infraction['player'].hasOwnProperty('gs_name')) {
        userName.text(infraction['player']['gs_name'])
    } else if (infraction['player'].hasOwnProperty('gs_id')) {
        userName.text('Unknown Player')
    } else if (infraction['player'].hasOwnProperty('ip')) {
        userName.text(infraction['player']['ip'])
    } else {
        userName.text('IP Address')
    }

    //Created
    createdAt.text(moment.unix(infraction['created']).format('LLL'));

    //A couple of flags

    if (infraction['flags'] & (INFRACTION.SYSTEM)) {
        systemTag.removeClass('is-hidden');
    }

    if (infraction['flags'] & (INFRACTION.REMOVED)) {
        removedTag.removeClass('is-hidden');
    }

    if (infraction['flags'] & (INFRACTION.VPN)) {
        vpnTag.removeClass('is-hidden');
    }

    if (infraction['flags'] & (INFRACTION.WEB)) {
        webTag.removeClass('is-hidden')
    }

   let isExpired = false;

    if (infraction.hasOwnProperty('time_left') && infraction['time_left'] <= 0 && infraction['flag'] & (INFRACTION.DEC_ONLINE_ONLY)) {
        isExpired = true;
    } else if (infraction.hasOwnProperty('expires') && Date.now() / 1000 >= infraction['expires']) {
        isExpired = true;
    }

    if (isExpired) {
        expiredTag.removeClass('is-hidden');
    }

    //Setup GSID and IP

    if (infraction['player'].hasOwnProperty('gs_id')) {
        idLabel.text(infraction['player']['gs_service'].charAt(0).toUpperCase() + infraction['player']['gs_service'].slice(1) + ' ID');
        
        let search = document.createElement('a');
        search.text = infraction['player']['gs_id'];
        search.setAttribute('href', '/infractions/?search=gs_id:"' + infraction['player']['gs_id'] + '"');

        idValue.append(search);

        if (infraction['player']['gs_service'] === 'steam') {
            let steamProfile = document.createElement('a');
            steamProfile.text = userName.text();
            userName.text('');
            steamProfile.setAttribute('href', 'http://steamcommunity.com/profiles/' + infraction['player']['gs_id']);
            steamProfile.setAttribute('target', '_blank');

            userName.append(steamProfile);
        }
    } else {
        idContainer.addClass('is-hidden');
    }

    if (infraction['player'].hasOwnProperty('ip')) {
        let search = document.createElement('a');
        search.text = infraction['player']['ip'];
        search.setAttribute('href', '/infractions/?search=ip:"' + infraction['player']['ip'] + '"');

        ipValue.append(search);
    } else {
        ipContainer.addClass('is-hidden');
    }

    // Setup the time
    timeValue.removeClass('has-tooltip-info');
    timeValue.removeAttr('data-tooltip');
    if (infraction['flags'] & (INFRACTION.PERMANENT)) {
        timeValue.text('Permanent');
    } else if (infraction['flags'] & (INFRACTION.SESSION)) {
        timeValue.text('Session');
    } else if (infraction['flags'] & (INFRACTION.DEC_ONLINE_ONLY)) {
        let s
        let tl = moment.duration(infraction['time_left'] * 1000);

        s = tl.humanize();

        s = s.charAt(0).toUpperCase() + s.slice(1);

        if (infraction.hasOwnProperty('orig_length')) {
            let ol = moment.duration(infraction['orig_length'] * 1000);

            s = s + ' of ' + ol.humanize();
        }

        if (infraction['time_left'] <= 0) {
            timeValue.text('Expired (Was ' + moment.duration(infraction['orig_length'] * 1000).humanize() + ')');
        }  else {
            if (infraction['time_left'] > 60) {
                // Display exact minutes left in a tooltip
                timeValue.addClass('has-tooltip-info');
                minutesLeft = (Math.round(moment.duration(infraction['time_left']) / 60) + " minutes left");
                timeValue.attr('data-tooltip', minutesLeft);
            }
            timeValue.text(s);
        }
    } else if (infraction.hasOwnProperty('expires')) {
        let exp = infraction['expires'] * 1000;
        let now = Date.now()
        let c = infraction['created'] * 1000;

        let d = moment.duration(exp - now);

        let ol = moment.duration(exp - c);

        let s;

        s = d.humanize();

        s = s.charAt(0).toUpperCase() + s.slice(1);

        timeValue.text(s + ' of ' + ol.humanize());

        if (exp - now <= 0) {
            timeValue.text('Expired (Was ' + ol.humanize() + ')');
        } else {
            // Display exact minutes left in a tooltip
            timeValue.addClass('has-tooltip-info');
            minutesLeft = Math.round(d / 60000) + " minutes left";
            timeValue.attr('data-tooltip', minutesLeft);
        }
    } else {
        timeValue.text('NO VALUE');
    }

    if (!(infraction['flags'] & (INFRACTION.SYSTEM)) && infraction.hasOwnProperty('admin')) {
        issuedValue.text((await get_admin(infraction['admin']))['admin_name']);
    } else {
        adminContainer.addClass('is-hidden');
    }

    // Global
    if (infraction['flags'] & (INFRACTION.GLOBAL)) {
        scopeValue.text('All Servers');
    } else if (infraction['flags'] & (INFRACTION.SUPER_GLOBAL)) {
        scopeValue.text('Community');
    } else {
        scopeValue.text('Only Origin Server');
    }

    if (infraction['flags'] & (INFRACTION.WEB) || !infraction.hasOwnProperty('server')) {
        serverValue.text('Web');
    } else {
        let sv = await gbRequest('GET', '/api/server/' + infraction['server'], null);

        if (!sv.ok) {
            throw 'Not OK!'
        }

        sv = await sv.json()

        if (sv.hasOwnProperty('friendly_name')) {
            serverValue.text(sv['friendly_name'] + ' (' + sv['ip'] + ')');
        } else {
            serverValue.text(sv['ip']);
        }
    }

    reasonValue.text(infraction['reason']);

    let t = false;

    function unhideIfTrue(b, a) {
        if (b) {
            t = true;
            a.removeClass('is-hidden');
        }
    }

    unhideIfTrue(infraction['flags'] & ALL_P_FLAGS === 0, warningFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.VOICE_BLOCK), voiceChatFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.CHAT_BLOCK), textChatFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.BAN), banFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.ADMIN_CHAT_BLOCK), adminChatFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.CALL_ADMIN_BAN), callAdminFlag);

    if (!t) {
        unhideIfTrue(true, warningFlag);
    }

    if (infraction['flags'] & (INFRACTION.REMOVED)) {
        removedC.removeClass('is-hidden');
        rR.text(infraction['removal_reason']);
        rOn.text(moment.unix(infraction['removed_on']).format('LLL'));

        if (infraction.hasOwnProperty('removed_by')) {
            rBy.text((await get_admin(infraction['removed_by']))['admin_name']);
        } else {
            rBy.text('System')
        }
    }

    addComments(mergeCommentFiles(infraction));

    prepareEditor(infraction);
}

function mergeCommentFiles(infraction) {
    let m = []

        for (let i = 0; i < infraction['comments'].length; i++) {
            let uid = 0;

            if (infraction['comments'][i].hasOwnProperty('author')) {
                uid = infraction['comments'][i]['author'];
            }

            let c = {
                'type': 'comment',
                'user': uid,
                'created': infraction['comments'][i]['created'],
                'private': infraction['comments'][i]['private'],
                'rendered': infraction['comments'][i]['rendered']
            }

            m.push(c);
        }


        for (let i = 0; i < infraction['files'].length; i++) {
            let uid = 0;

            if (infraction['files'][i].hasOwnProperty('uploaded_by')) {
                uid = infraction['files'][i]['uploaded_by'];
            }

            let f = {
                'type': 'file',
                'user': uid,
                'created': infraction['files'][i]['created'],
                'private': infraction['files'][i]['private'],
                'rendered': infraction['files'][i]['rendered']
            }

            m.push(f)
        }


    m.sort(function (a, b) {
            return a['created'] - b['created']
    })

    return m;
}


function addComments(renderableComments) {
    for (let i = 0; i < renderableComments.length; i++) {
        $('#commentCount').text(i + 1);
        let rc = renderableComments[i];

        let cArt = document.createElement('article');
        cArt.classList.add('media');

        let leftFigure = document.createElement('figure');
        leftFigure.classList.add('media-left');

        let imageWrapper = document.createElement('p');
        imageWrapper.classList.add('image', 'is-48x48');

        let avatarImage = document.createElement('img');
        avatarImage.classList.add('is-rounded', 'set-default-on-error');
        avatarImage.setAttribute('src', '/static/images/fallback_av.png');

        imageWrapper.appendChild(avatarImage);
        leftFigure.appendChild(imageWrapper);

        let content = document.createElement('div');
        content.classList.add('media-content');

        let innerContent = document.createElement('div')
        innerContent.classList.add('content');

        let textWrapper = document.createElement('p');

        let username = document.createElement('strong');
        let date = document.createElement('small');
        let priv = document.createElement('small');

        username.classList.add('text-primary')

        $(username).text('Loading');
        $(date).text(' ' + moment.unix(rc['created']).format('LLL') + ' ');

        if (rc['private']) {
            $(priv).text('(Private)')
            priv.classList.add('has-text-danger');
        }

        let br = document.createElement('br');
        let messageContent = document.createElement('span');

        $(messageContent).html(rc['rendered']);

        textWrapper.append(username, date, priv, br, messageContent);

        innerContent.appendChild(textWrapper);
        content.appendChild(innerContent);
        cArt.appendChild(leftFigure);
        cArt.appendChild(content);

        commentContainer.append(cArt);

        if (rc['user'] === 0) {
            $(username).text('System');
        } else {
            get_admin(rc['user']).then(function (adm) {
                $(username).text(adm['admin_name']);

                if (!adm.hasOwnProperty('avatar_id')) {
                    return;
                }

                $(avatarImage).attr('src', '/file/uploads/' + adm['avatar_id'] + '/avatar.webp');
            })
        }

    }

    if (renderableComments.length <= 3) {
        let cind = $('#commentState');
        cind.removeClass('fa-sort-up');
        cind.addClass('fa-sort-down');
        commentContainer.removeClass('is-hidden');
    }
}

function wrapSetupView(j, start=0) {
    resetViewModal();

    setupViewModal(j).then(function () {

                function _showModal() {
                    unsetLoading();
                    $('#infraction_view_modal').addClass('is-active');
                    $('#htmlRoot').addClass('is-clipped');
                }

                let dur = 200 - ((new Date()).getTime() - start);

                // If it was quicker than 200 ms, then stall for the time left to reduce flicker
                if (dur > 0) {
                    setTimeout(_showModal, dur)
                } else {
                    _showModal();
                }
            }).catch(genericError);
}

function _openInfraction(infraction_id, start, skip_push=false) {

    if (!skip_push) {
        setInfractionUri(infraction_id);
    }

    gbRequest('GET', '/api/infractions/' + infraction_id + '/info', null, false).then(function (r) {
        r.json().then(function (j) {
            wrapSetupView(j, start)
        }).catch(genericError);
    }).catch(genericError);
}

function openInfraction(infraction_id, skip_push=false) {
    closeModals();

    setLoading();

    _openInfraction(infraction_id, (new Date()).getTime(), skip_push)
}

function setInfractionUri(infraction_id) {
    let urlParams = new URLSearchParams(window.location.search);

    let nurl;

    if (infraction_id) {
        nurl = '/infractions/' + infraction_id + '/';
    } else {
        nurl = '/infractions/';
    }


    let a = false;

    function nc() {
        if (a) {
            return '&'
        } else {
            a = true;
            return '?'
        }
    }

    if (urlParams.has('page')) {
        nurl = nurl + nc() + 'page=' + urlParams.get('page');
    }

    if (urlParams.has('search')) {
        nurl = nurl + nc() + 'search=' + urlParams.get('search');
    }

    let state = 'Infraction'

    if (infraction_id) {
        state = infraction_id;
    }

    window.history.pushState({'gb_state': state}, 'GFLBans - Infraction', nurl);
}

function restoreInfractionUri() {
    setInfractionUri(null);
}

$(document).ready(function () {
    $('#commentToggle').click(function () {
        let cind = $('#commentState')

        if (cind.hasClass('fa-sort-up')) {
            cind.removeClass('fa-sort-up');
            cind.addClass('fa-sort-down');
            commentContainer.removeClass('is-hidden');
        } else {
            cind.addClass('fa-sort-up');
            cind.removeClass('fa-sort-down');
            commentContainer.addClass('is-hidden');
        }
    })

    $('#ivm-back').click(restoreInfractionUri)
    $('#ivm-close').click(restoreInfractionUri)

    window.onpopstate = function (ev) {
        if (ev.state.hasOwnProperty('gb_state')) {
            if (ev.state['gb_state'] === 'Infraction' && $('#infraction_view_modal').hasClass('is-active')) {
                closeModals();
            } else {
                openInfraction(ev.state['gb_state'], true);
            }
        }
    }
})