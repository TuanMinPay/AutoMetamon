$(document).ready(function () {

    let playBtn = $('#play');
    $(":input").on("keyup", function (e) {
        // e.preventDefault();
        let name = $('#name').val();
        let address = $('#address').val();
        let sign = $('#sign').val();
        let msg = $('#msg').val();
        if (name && address && sign && msg) {
            playBtn.prop("disabled", false);
        } else {
            playBtn.prop("disabled", true);
        }
    });
    playBtn.click(async function (e) {
        e.preventDefault();
        let name = $('#name').val();
        let address = $('#address').val();
        let sign = $('#sign').val();
        let msg = $('#msg').val();
        let autoLevel = $('#autoLevel').is(':checked');
        let autoMintEgg = $('#autoMintEgg').is(':checked');
        let skipBattles = $('#skipBattles').is(':checked');
        $('#playing').show();
        $('#play').hide();
        await $.ajax({
            type: "POST",
            contentType: "application/json",
            url: '/auto/metamon/',
            data: JSON.stringify({
                name,
                address,
                sign,
                msg,
                autoLevel,
                autoMintEgg,
                skipBattles
            }),
            dataType: "json",
            success: function (data) {
                $('#playing').hide();
                $('#play').show();
                $('#logging').val(data.msg);
            },
            error: function (e) {
                $('#playing').hide();
                $('#play').show();
                $('#logging').val(e.responseText);
            }
         });
    });
});