# import spaces

import os

import torch
import gradio as gr

import sys
sys.path.append('./')
from videollama2.constants import MMODAL_TOKEN_INDEX, DEFAULT_MMODAL_TOKEN
from videollama2.conversation import conv_templates, SeparatorStyle, Conversation
from videollama2.model.builder import load_pretrained_model
from videollama2.mm_utils import KeywordsStoppingCriteria, tokenizer_MMODAL_token, get_model_name_from_path, process_image, process_video


title_markdown = ("""
<div style="display: flex; justify-content: center; align-items: center; text-align: center;">
  <a href="https://github.com/DAMO-NLP-SG/VideoLLaMA2" style="margin-right: 20px; text-decoration: none; display: flex; align-items: center;">
    <img src="https://s2.loli.net/2024/06/03/D3NeXHWy5az9tmT.png" alt="VideoLLaMA 2 🔥🚀🔥" style="max-width: 120px; height: auto;">
  </a>
  <div>
    <h1 >VideoLLaMA 2: Advancing Spatial-Temporal Modeling and Audio Understanding in Video-LLMs</h1>
    <h5 style="margin: 0;">If this demo please you, please give us a star ⭐ on Github or 💖 on this space.</h5>
  </div>
</div>


<div align="center">
    <div style="display:flex; gap: 0.25rem; margin-top: 10px;" align="center">
        <a href="https://github.com/DAMO-NLP-SG/VideoLLaMA2"><img src='https://img.shields.io/badge/Github-VideoLLaMA2-9C276A'></a>
        <a href="https://arxiv.org/pdf/2406.07476.pdf"><img src="https://img.shields.io/badge/Arxiv-2406.07476-AD1C18"></a>
        <a href="https://github.com/DAMO-NLP-SG/VideoLLaMA2/stargazers"><img src="https://img.shields.io/github/stars/DAMO-NLP-SG/VideoLLaMA2.svg?style=social"></a>
    </div>
</div>
""")


block_css = """
#buttons button {
    min-width: min(120px,100%);
    color: #9C276A
}
"""


tos_markdown = ("""
### Terms of use
By using this service, users are required to agree to the following terms:
The service is a research preview intended for non-commercial use only. It only provides limited safety measures and may generate offensive content. It must not be used for any illegal, harmful, violent, racist, or sexual purposes. The service may collect user dialogue data for future research.
Please click the "Flag" button if you get any inappropriate answer! We will collect those to keep improving our moderator.
For an optimal experience, please use desktop computers for this demo, as mobile devices may compromise its quality.
""")


learn_more_markdown = ("""
### License
This project is released under the Apache 2.0 license as found in the LICENSE file. The service is a research preview intended for non-commercial use ONLY, subject to the model Licenses of LLaMA and Mistral, Terms of Use of the data generated by OpenAI, and Privacy Practices of ShareGPT. Please get in touch with us if you find any potential violations.
""")


plum_color = gr.themes.colors.Color(
    name='plum',
    c50='#F8E4EF',
    c100='#E9D0DE',
    c200='#DABCCD',
    c300='#CBA8BC',
    c400='#BC94AB',
    c500='#AD809A',
    c600='#9E6C89',
    c700='#8F5878',
    c800='#804467',
    c900='#713056',
    c950='#662647',
)


class Chat:
    def __init__(self, model_path, conv_mode, model_base=None, load_8bit=False, load_4bit=False):
        # disable_torch_init()
        model_name = get_model_name_from_path(model_path)
        self.tokenizer, self.model, processor, context_len = load_pretrained_model(
            model_path, model_base, model_name,
            load_8bit, load_4bit,
            offload_folder="save_folder")
        self.processor = processor
        self.conv_mode = conv_mode
        self.conv = conv_templates[conv_mode].copy()

    def get_prompt(self, qs, state):
        state.append_message(state.roles[0], qs)
        state.append_message(state.roles[1], None)
        return state

    # @spaces.GPU(duration=120)
    @torch.inference_mode()
    def generate(self, tensor: list, modals: list, prompt: str, first_run: bool, state, temperature, top_p, max_output_tokens):
        # TODO: support multiple turns of conversation.
        assert len(tensor) == len(modals)

        # 1. prepare model, tokenizer, and processor.
        tokenizer, model, processor = self.tokenizer, self.model, self.processor

        # 2. text preprocess (tag process & generate prompt).
        state = self.get_prompt(prompt, state)
        prompt = state.get_prompt()

        input_ids = tokenizer_MMODAL_token(prompt, tokenizer, MMODAL_TOKEN_INDEX[modals[0]], return_tensors='pt')
        input_ids = input_ids.unsqueeze(0).to(self.model.device)

        # 3. generate response according to visual signals and prompts. 
        stop_str = self.conv.sep if self.conv.sep_style in [SeparatorStyle.SINGLE] else self.conv.sep2
        # keywords = ["<s>", "</s>"]
        keywords = [stop_str]
        stopping_criteria = KeywordsStoppingCriteria(keywords, tokenizer, input_ids)

        with torch.inference_mode():
            output_ids = model.generate(
                input_ids,
                images_or_videos=tensor,
                modal_list=modals,
                do_sample=True,
                temperature=temperature,
                top_p=top_p,
                max_new_tokens=max_output_tokens,
                use_cache=True,
                stopping_criteria=[stopping_criteria],
            )

        outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
        print(outputs)
        return outputs, state


# @spaces.GPU(duration=120)
def generate(image, video, state, state_, textbox_in, temperature, top_p, max_output_tokens, dtype=torch.float16):
    if not textbox_in:
        if len(state_.messages) > 0:
            textbox_in = state_.messages[-1][1]
            state_.messages.pop(-1)
        else:
            assert "Please enter instruction"

    image = image if image else "none"
    video = video if video else "none"
    assert not (os.path.exists(image) and os.path.exists(video))

    tensor = []
    modals = []

    if type(state) is not Conversation:
        state = conv_templates[conv_mode].copy()
        state_ = conv_templates[conv_mode].copy()

    first_run = False if len(state.messages) > 0 else True

    text_en_in = textbox_in.replace("picture", "image")

    num_frames = handler.model.config.num_frames if hasattr(handler.model.config, "num_frames") else NUM_FRAMES

    processor = handler.processor
    if os.path.exists(image) and not os.path.exists(video):
        tensor.append(process_image(image, processor).to(handler.model.device, dtype=dtype))
        modals.append('IMAGE')
    if not os.path.exists(image) and os.path.exists(video):
        tensor.append(process_video(video, processor, num_frames=num_frames, sample_scheme='fps').to(handler.model.device, dtype=dtype))
        modals.append('VIDEO')
    if os.path.exists(image) and os.path.exists(video):
        raise NotImplementedError("Not support image and video at the same time")

    # BUG: Only support single video and image inference now.
    if os.path.exists(image) and not os.path.exists(video):
        text_en_in = text_en_in.replace(DEFAULT_MMODAL_TOKEN['IMAGE'], '').strip()
        text_en_in = DEFAULT_MMODAL_TOKEN['IMAGE'] + '\n' + text_en_in
    if not os.path.exists(image) and os.path.exists(video):
        text_en_in = text_en_in.replace(DEFAULT_MMODAL_TOKEN['VIDEO'], '').strip()
        text_en_in = DEFAULT_MMODAL_TOKEN['VIDEO'] + '\n' + text_en_in
    if os.path.exists(image) and os.path.exists(video):
        text_en_in = text_en_in.replace(DEFAULT_MMODAL_TOKEN['VIDEO'], '').strip()
        text_en_in = DEFAULT_MMODAL_TOKEN['VIDEO'] + '\n' + text_en_in
    text_en_out, state_ = handler.generate(tensor, modals, text_en_in, first_run=first_run, state=state_, temperature=temperature, top_p=top_p, max_output_tokens=max_output_tokens)
    state_.messages[-1] = (state_.roles[1], text_en_out)

    text_en_out = text_en_out.split('#')[0]
    textbox_out = text_en_out

    show_images = ""
    if os.path.exists(image):
        show_images += f'<img src="./file={image}" style="display: inline-block;width: 250px;max-height: 400px;">'
    if os.path.exists(video):
        show_images += f'<video controls playsinline width="500" style="display: inline-block;"  src="./file={video}"></video>'

    state.append_message(state.roles[0], textbox_in + "\n" + show_images)
    state.append_message(state.roles[1], textbox_out)

    # BUG: only support single turn conversation now.
    state_.messages.pop(-1)
    state_.messages.pop(-1)

    return (gr.update(value=image if os.path.exists(image) else None, interactive=True), 
            gr.update(value=video if os.path.exists(video) else None, interactive=True), 
            state.to_gradio_chatbot(), state, state_)


def regenerate(state, state_):
    state.messages.pop(-1)
    state.messages.pop(-1)
    if len(state.messages) > 0:
        return state.to_gradio_chatbot(), state, state_
    return state.to_gradio_chatbot(), state, state_


def clear_history(state, state_):
    state = conv_templates[conv_mode].copy()
    state_ = conv_templates[conv_mode].copy()
    return (gr.update(value=None, interactive=True),
            gr.update(value=None, interactive=True),
            state.to_gradio_chatbot(), state, state_, 
            gr.update(value=None, interactive=True))


# BUG of Zero Environment
# 1. The environment is fixed to torch==2.0.1+cu117, gradio>=4.x.x
# 2. The operation or tensor which requires cuda are limited in those functions wrapped via spaces.GPU
# 3. The function can't return tensor or other cuda objects.

conv_mode = "llama_2"
model_path = 'DAMO-NLP-SG/VideoLLaMA2-7B-16F'

device = torch.device("cuda")

handler = Chat(model_path, conv_mode=conv_mode, load_8bit=False, load_4bit=True)

textbox = gr.Textbox(show_label=False, placeholder="Enter text and press ENTER", container=False)

theme = gr.themes.Default(primary_hue=plum_color)
# theme.update_color("primary", plum_color.c500)
theme.set(slider_color="#9C276A")
theme.set(block_title_text_color="#9C276A")
theme.set(block_label_text_color="#9C276A")
theme.set(button_primary_text_color="#9C276A")
# theme.set(button_secondary_text_color="*neutral_800")


with gr.Blocks(title='VideoLLaMA 2 🔥🚀🔥', theme=theme, css=block_css) as demo:
    gr.Markdown(title_markdown)
    state = gr.State()
    state_ = gr.State()

    with gr.Row():
        with gr.Column(scale=3):
            image = gr.Image(label="Input Image", type="filepath")
            video = gr.Video(label="Input Video")

            with gr.Accordion("Parameters", open=True) as parameter_row:
                # num_beams = gr.Slider(
                #     minimum=1,
                #     maximum=10,
                #     value=1,
                #     step=1,
                #     interactive=True,
                #     label="beam search numbers",
                # )

                temperature = gr.Slider(
                    minimum=0.1,
                    maximum=1.0,
                    value=0.2,
                    step=0.1,
                    interactive=True,
                    label="Temperature",
                )

                top_p = gr.Slider(
                        minimum=0.0,
                        maximum=1.0,
                        value=0.7,
                        step=0.1,
                        interactive=True,
                        label="Top P",
                )

                max_output_tokens = gr.Slider(
                    minimum=64,
                    maximum=1024,
                    value=512,
                    step=64,
                    interactive=True,
                    label="Max output tokens",
                )

        with gr.Column(scale=7):
            chatbot = gr.Chatbot(label="VideoLLaMA 2", bubble_full_width=True, height=750)
            with gr.Row():
                with gr.Column(scale=8):
                    textbox.render()
                with gr.Column(scale=1, min_width=50):
                    submit_btn = gr.Button(value="Send", variant="primary", interactive=True)
            with gr.Row(elem_id="buttons") as button_row:
                upvote_btn     = gr.Button(value="👍  Upvote", interactive=True)
                downvote_btn   = gr.Button(value="👎  Downvote", interactive=True)
                # flag_btn     = gr.Button(value="⚠️  Flag", interactive=True)
                # stop_btn     = gr.Button(value="⏹️  Stop Generation", interactive=False)
                regenerate_btn = gr.Button(value="🔄  Regenerate", interactive=True)
                clear_btn      = gr.Button(value="🗑️  Clear history", interactive=True)

    with gr.Row():
        with gr.Column():
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            gr.Examples(
                examples=[
                    [
                        f"{cur_dir}/examples/extreme_ironing.jpg",
                        "What happens in this image?",
                    ],
                    [
                        f"{cur_dir}/examples/waterview.jpg",
                        "What are the things I should be cautious about when I visit here?",
                    ],
                    [
                        f"{cur_dir}/examples/desert.jpg",
                        "If there are factual errors in the questions, point it out; if not, proceed answering the question. What’s happening in the desert?",
                    ],
                ],
                inputs=[image, textbox],
            )
        with gr.Column():
            gr.Examples(
                examples=[
                    [
                        f"{cur_dir}/../../assets/cat_and_chicken.mp4",
                        "What happens in this video?",
                    ],
                    [
                        f"{cur_dir}/../../assets/sora.mp4",
                        "Please describe this video.",
                    ],
                    [
                        f"{cur_dir}/examples/sample_demo_1.mp4",
                        "What does the baby do?",
                    ],
                ],
                inputs=[video, textbox],
            )

    gr.Markdown(tos_markdown)
    gr.Markdown(learn_more_markdown)

    submit_btn.click(
        generate, 
        [image, video, state, state_, textbox, temperature, top_p, max_output_tokens],
        [image, video, chatbot, state, state_])

    regenerate_btn.click(
        regenerate, 
        [state, state_], 
        [chatbot, state, state_]).then(
        generate, 
        [image, video, state, state_, textbox, temperature, top_p, max_output_tokens], 
        [image, video, chatbot, state, state_])

    clear_btn.click(
        clear_history, 
        [state, state_],
        [image, video, chatbot, state, state_, textbox])

demo.launch()
